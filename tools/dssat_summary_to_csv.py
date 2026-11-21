#!/usr/bin/env python3
"""Read the yields out of DSSAT Summary.OUT files and write model_years.csv for csv_to_data.py (docs/TUTORIAL.md).

    python3 tools/dssat_summary_to_csv.py --index runs_index.csv --crop MZ --out my_tables/model_years.csv

runs_index.csv (UTF-8, header row) lists one Summary.OUT per cell, water kind and model version:
    cell_id,water,which,path
    N36E117a,rf,calibrated,/data/runs/cal/N36E117a/rf/Summary.OUT
    N36E117a,rf,uncalibrated,/data/runs/base/N36E117a/rf/Summary.OUT
  which = calibrated (the unit's final settings) or uncalibrated (the starting settings).
  A relative path is read from the folder of runs_index.csv.

model_years.csv gets one row per cell, water kind, which and year:
    cell_id,water,which,year,yield_t_ha

How a Summary.OUT row becomes a yield:
  - only rows whose crop code (CR) is --crop are used (MZ maize, WH wheat, SB soybean, RI rice, ...);
    fallow rows (FA) and other crops in a rotation are skipped;
  - the year is the harvest year (HDAT, else MDAT when HDAT is missing, else PDAT) with --year-from harvest
    (default), or the planting year (PDAT) with --year-from planting. Use the same rule as your reported yields.
    A date counts only in the DSSAT form YYYYDDD (exactly 7 digits, day of year 1-365, 366 only in a leap year);
    anything else counts as missing;
  - --first-year / --last-year skip seasons outside those years (e.g. spin-up years before your page.years);
  - HWAM (kg/ha), a whole number 0 or more  ->  HWAM / 1000 t/ha;
  - HWAM exactly -99 but the crop was planted (the season failed, no grain)  ->  0 with --failed zero (default),
    or an empty cell ("no value") with --failed missing;
  - any other HWAM (blank, '*****', another negative number)  ->  that row is skipped and counted in a warning;
  - no valid planting date  ->  no row (the season never started).
  If one cell, water kind and which has two rows for the same year, that year is written empty and a warning is
  printed: the script never guesses which one is right.

Files listed in the index that do not exist yet, in a folder that does exist (e.g. the calibrated runs of units not
calibrated yet), are counted and skipped; that is normal during a run (exit code 0). Any other problem is an error:
a file that cannot be read or has no '@' header with the needed columns, or a path whose folder does not exist or
cannot be entered. Errors are listed, the exit code is 1, and model_years.csv is NOT replaced (the last good table
stays, so an export chained after this with && does not run on a partial table). A last line without its newline
(DSSAT may still be writing the file) is skipped and counted. model_years.csv is written to a temporary name and
then renamed.

The file is read by column position, from the '@' header line: each value ends where its column name ends (the
name includes its trailing dots, e.g. 'TNAM.....'). DSSAT 4.8 dates are YYYYDDD. Only the Python standard library is used.
"""
import argparse
import csv
import os
import re
import sys
from pathlib import Path

NEED = ("CR", "PDAT", "MDAT", "HDAT", "HWAM")


def spans(header):
    """Column name -> (start, end) in the line. A value sits between the end of the previous name and the end of
    its own name (DSSAT right-aligns numbers under the end of the name; text starts under the name)."""
    out, prev = {}, 1                       # position 0 is the '@'
    for m in re.finditer(r"\S+", header):
        if m.group() == "@":
            prev = m.end()
            continue
        name = m.group().rstrip(".")
        if name and name not in out:
            out[name] = (prev, m.end())
        prev = m.end()
    return out


INT_RE = re.compile(r"^-?[0-9]+$")


def as_int(text):
    """A whole number written as one (e.g. '7551', '-99'); anything else ('', '*****', '7.5') -> None."""
    return int(text) if INT_RE.match(text) else None


DATE_RE = re.compile(r"^[0-9]{7}$")


def date_year(text):
    """A DSSAT date written as exactly 7 digits YYYYDDD (year 1000-9999, day of year 1-365, or 366 in a leap year)
    -> its year; -99, 0 or anything else -> None."""
    if not DATE_RE.match(text):
        return None
    y, d = int(text[:4]), int(text[4:])
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    if y < 1000 or not 1 <= d <= (366 if leap else 365):
        return None
    return y


def read_summary(path, crop, year_from, failed, first, last, count):
    """({year: t/ha or None}, status) for one Summary.OUT; status 'ok', 'missing' (no such file) or 'bad' (exists
    but cannot be read or has no usable header). Two rows for the same year -> None for that year."""
    got, twice = {}, set()
    try:
        os.stat(path)
    except FileNotFoundError:
        # "not there yet": the file (or its run folder) does not exist yet, normal while the run goes on. A wrong
        # path of another kind (a file where a folder should be, a folder we may not enter) is an error below.
        return {}, "missing"
    except OSError as e:
        count["bad_files"].append(f"{path}: cannot read it ({e.strerror})")
        return {}, "bad"
    try:
        fh = open(path, encoding="latin-1")
    except OSError as e:
        count["bad_files"].append(f"{path}: cannot read it ({e.strerror})")
        return {}, "bad"
    cols = None
    with fh:
        try:
            lines = list(fh)
        except OSError as e:
            count["bad_files"].append(f"{path}: cannot read it ({e.strerror})")
            return {}, "bad"
    if lines and not lines[-1].endswith("\n"):
        lines = lines[:-1]                  # a last line without its newline: DSSAT may still be writing it
        count["partial"] += 1
    for line in lines:
        if line.startswith("@"):
            cols = spans(line.rstrip("\n"))
            lost = [c for c in NEED if c not in cols]
            if lost:
                count["bad_files"].append(f"{path}: the '@' header has no column {lost}")
                return {}, "bad"
            continue
        if cols is None or not line.strip() or line[0] in "*!$":
            continue
        v = {c: line[a:b].strip() for c, (a, b) in cols.items() if c in NEED}
        if v["CR"] != crop:
            continue
        hwam = as_int(v["HWAM"])
        py, my, hy = (date_year(v[c]) for c in ("PDAT", "MDAT", "HDAT"))
        if py is None:
            if v["PDAT"] not in ("-99", "0"):
                count["bad_dates"] += 1
            continue                        # never planted (or an unreadable planting date): no season
        if year_from == "planting":
            year = py
        else:
            year = hy or my or py
        if (first is not None and year < first) or (last is not None and year > last):
            count["outside"] += 1
            continue
        if hwam is not None and hwam >= 0:
            y = hwam / 1000.0
        elif hwam == -99:
            y = 0.0 if failed == "zero" else None
        else:
            count["bad_hwam"] += 1
            if len(count["bad_hwam_eg"]) < 3:
                count["bad_hwam_eg"].append(f"{path}: HWAM '{v['HWAM']}' in {year}")
            continue
        if year in got or year in twice:
            twice.add(year)
            got[year] = None
        else:
            got[year] = y
    if cols is None:
        count["bad_files"].append(f"{path}: no '@' header line (not a Summary.OUT?)")
        return {}, "bad"
    for year in sorted(twice):
        count["warnings"].append(f"{path}: two {crop} rows for {year}; that year is left empty")
    return got, "ok"


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--index", required=True, help="CSV with cell_id, water, which, path")
    a.add_argument("--crop", required=True, help="DSSAT crop code in the CR column, e.g. MZ, WH, SB, RI")
    a.add_argument("--out", required=True, help="model_years.csv to write")
    a.add_argument("--year-from", choices=("harvest", "planting"), default="harvest")
    a.add_argument("--failed", choices=("zero", "missing"), default="zero",
                   help="a planted season with no grain (HWAM -99): 0 t/ha (default) or no value")
    a.add_argument("--first-year", type=int, help="skip seasons before this year (e.g. spin-up years)")
    a.add_argument("--last-year", type=int, help="skip seasons after this year")
    args = a.parse_args()
    crop = args.crop.strip().upper()
    index = Path(args.index)
    if args.first_year is not None and args.last_year is not None and args.first_year > args.last_year:
        sys.exit("--first-year is after --last-year")
    count = {"bad_files": [], "warnings": [], "bad_dates": 0, "bad_hwam": 0, "bad_hwam_eg": [], "outside": 0,
             "partial": 0}

    try:
        fh = open(index, newline="", encoding="utf-8-sig")
    except OSError as e:
        sys.exit(f"{index}: cannot open it ({e.strerror})")
    jobs, seen = [], {}
    with fh:
        rows = csv.DictReader(fh)
        if {"cell_id", "water", "which", "path"} - set(rows.fieldnames or []):
            sys.exit(f"{index}: needs the columns cell_id, water, which, path")
        for n, r in enumerate(rows, start=2):
            cid, water, which, p = ((r[k] or "").strip() for k in ("cell_id", "water", "which", "path"))
            if not cid or not water or not p:
                sys.exit(f"{index} line {n}: cell_id, water and path must not be empty")
            if which not in ("calibrated", "uncalibrated"):
                sys.exit(f"{index} line {n}: which must be 'calibrated' or 'uncalibrated' (got '{which}')")
            key = (cid, water, which)
            if key in seen:
                sys.exit(f"{index} line {n}: {cid} / {water} / {which} is already on line {seen[key]}")
            seen[key] = n
            path = Path(p) if os.path.isabs(p) else index.parent / p
            jobs.append((cid, water, which, path))
    if not jobs:
        sys.exit(f"{index}: no rows")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.name}.{os.getpid()}.tmp")
    n_rows = n_zero = n_empty = n_files_empty = n_missing = 0
    kind_seen, kind_missing = {}, {}
    with open(tmp, "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["cell_id", "water", "which", "year", "yield_t_ha"])
        for k, (cid, water, which, path) in enumerate(jobs, start=1):
            got, status = read_summary(path, crop, args.year_from, args.failed, args.first_year, args.last_year, count)
            n_missing += status == "missing"
            kind_seen[which] = kind_seen.get(which, 0) + 1
            kind_missing[which] = kind_missing.get(which, 0) + (status == "missing")
            if status == "ok" and not got:
                n_files_empty += 1
            for year in sorted(got):
                y = got[year]
                w.writerow([cid, water, which, year, "" if y is None else f"{y:.3f}"])   # kg/ha / 1000: exact
                n_rows += 1
                n_zero += y == 0
                n_empty += y is None
            if k % 5000 == 0:
                print(f"... {k} / {len(jobs)} files", file=sys.stderr)
    if count["bad_files"]:
        tmp.unlink()                        # keep the last good table: the export after this must not use a partial one
    else:
        os.replace(tmp, out)

    warnings = count["warnings"]
    if count["bad_hwam"]:
        warnings.append(f"{count['bad_hwam']} row(s) skipped because HWAM is not a whole number >= 0 or -99, e.g. "
                        + "; ".join(count["bad_hwam_eg"]))
    if count["bad_dates"]:
        warnings.append(f"{count['bad_dates']} {crop} row(s) skipped because the planting date is not a YYYYDDD date")
    if count["partial"]:
        warnings.append(f"{count['partial']} file(s) end in a half-written line (DSSAT still writing?); that line "
                        f"was skipped")
    for x in warnings[:20]:
        print("WARNING ", x, file=sys.stderr)
    if len(warnings) > 20:
        print(f"WARNING  ... and {len(warnings) - 20} more", file=sys.stderr)
    for x in count["bad_files"][:20]:
        print("ERROR   ", x, file=sys.stderr)
    print(f"{'NOT written (errors above; the last good table is kept)' if count['bad_files'] else 'written'} "
          f"{out}: {n_rows} rows from {len(jobs)} listed files ({n_zero} seasons with 0 t/ha, {n_empty} empty "
          f"years, {n_files_empty} files with no {crop} season"
          + (f", {count['outside']} seasons outside the chosen years skipped" if count["outside"] else "") + ").")
    if n_missing:
        print(f"{n_missing} listed file(s) not there yet (skipped; normal while the run goes on).")
    for which, n in kind_seen.items():
        if n and kind_missing.get(which) == n:
            print(f"WARNING  none of the {n} '{which}' files exists yet: if the run has already made some, check the "
                  f"paths in the index", file=sys.stderr)
    if count["bad_files"]:
        print(f"{len(count['bad_files'])} listed file(s) could not be read (errors above); fix them.",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
