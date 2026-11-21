#!/usr/bin/env python3
"""Turn your run's tables into the page's data folder (docs/TUTORIAL.md, part 1).

    python3 tools/csv_to_data.py --tables my_tables/ --out app/public/data

my_tables/ holds (UTF-8 CSV with a header row; docs/TUTORIAL.md shows each one):
  texts.json          your texts and page settings, written by hand once (copy the example's texts.json)
  units.csv           unit_id, name_en, name_zh, parent_en, parent_zh, state, cal_start, cal_end, val_start, val_end,
                      note_en, note_zh, progress_done, progress_total
                      state = waiting, calibrating, calibrated or left_out
  cells.csv           cell_id, water, lat, lon, unit_id, area_ha, state
                      state = waiting, calibrated, left_out or no_season (empty: calibrated when its unit is, else waiting)
  reported.csv        unit_id, year, yield_t_ha, usable (true/false; empty = true)
  model_years.csv     cell_id, water, which, year, yield_t_ha   (tools/dssat_summary_to_csv.py writes it)
                      which = calibrated or uncalibrated; an empty yield = no value; 0 = a season with no grain
  final_settings.csv  unit_id, then one column per setting id in texts.json page.settings (calibrated units only)

What it works out for you (the rules are in docs/DATA_FORMAT.md, and tools/check_data.py checks them again):
  - each unit's yearly model yield from its cells, weighted by crop area (needs cells with >= 90 % of the area);
  - each calibrated unit's scores over its calibration and validation years: n, yield ratio, R;
  - the map values of every cell: crop area, calibrated and uncalibrated yield over its unit's calibration and
    validation years, and its unit's yield ratio and R.
Each export goes into its own folder data/v/<data_version>/ (cells.json, units.json, cell_years/); manifest.json is
written last and names that folder, so a page never mixes two exports. If nothing changed since the last export,
nothing is written (open pages then need not download everything again). Old version folders are removed, except
the one before and any that stopped being current less than 30 minutes ago (a page that read the old manifest a
moment ago can still finish); v/.history.json records when each version was current. Two exports into the same
folder at once wait for each other (a lock file data/.export.lock).
With --dry-run it only checks and reports, and writes nothing. Only the Python standard library is used.
"""
import argparse
import csv
import json
import math
import os
import re
import secrets
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

try:
    import fcntl                # an exclusive lock so two exports into the same folder never mix (not on Windows)
except ImportError:             # pragma: no cover
    fcntl = None

MISSING = {"", "nan", "na", "n/a", "null", "none"}
UNIT_STATES = ("waiting", "calibrating", "calibrated", "left_out")
CELL_STATES = {"waiting": 0, "calibrated": 1, "left_out": 2, "no_season": 3}
COVER = 0.9                    # a unit-year needs cells with at least 90 % of the area of the unit's counted cells
DIGITS = 6                     # yields are kept with up to 6 decimals (a positive yield never becomes 0)
KEEP_S = 30 * 60               # old version folders younger than this are kept
VERSION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z(_[0-9]+)?$")
KINDS = ("calibrated", "uncalibrated")


def write(path, obj):
    """Write JSON atomically: a temporary file first (a name no other writer uses), then rename, so a reader never
    sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def keep(v):
    """A yield as stored: 6 decimals, but a positive yield never becomes 0."""
    r = round(v, DIGITS)
    return v if v > 0 and r == 0 else r


def https_url(u):
    """True for an https address with a host, e.g. https://crops.example.org/."""
    if not isinstance(u, str):
        return False
    try:
        p = urlsplit(u)
        p.port                                        # a port that is not a number raises ValueError
    except ValueError:
        return False
    host = p.hostname or ""
    if p.scheme != "https" or not host or any(ch.isspace() for ch in u) or any(ch in host for ch in "/\\@?#%"):
        return False
    if re.fullmatch(r"[0-9.]+", host):           # a dotted number address: four parts, each 0-255
        parts = host.split(".")
        return len(parts) == 4 and all(x.isdigit() and int(x) <= 255 for x in parts)
    return True                                  # names (also non-Latin ones) and [IPv6] addresses


def num(text, where, marker_check=True):
    """A number, or None for an empty or missing cell. Stops with a clear message on anything else
    (and on -99, -9999 ...: those are "missing" markers, write an empty cell instead)."""
    t = (text or "").strip()
    if t.lower() in MISSING:
        return None
    try:
        x = float(t)
    except ValueError:
        sys.exit(f"{where}: '{t}' is not a number (leave the cell empty for 'no value')")
    if not math.isfinite(x) or (marker_check and x <= -99):
        sys.exit(f"{where}: '{t}' looks like a 'missing' marker; leave the cell empty instead")
    return x


def whole(text, where):
    """A whole number >= 0, or None for an empty cell. Stops with a plain message on anything else."""
    t = (text or "").strip()
    if t.lower() in MISSING:
        return None
    try:
        x = float(t)
    except ValueError:
        x = float("nan")
    if not math.isfinite(x) or not x.is_integer() or x < 0:
        sys.exit(f"{where}: '{t}' is not a whole number (leave the cell empty if you do not know it)")
    return int(x)


def covered_enough(have, total):
    """The 90 % rule, with room for rounding: 0.3 + 0.6 of 1.0 counts as 90 %."""
    return total > 0 and have > 0 and have >= COVER * total - 1e-9 * total


def year(text, where):
    x = num(text, where)
    if x is None or not x.is_integer():
        sys.exit(f"{where}: '{text}' is not a year")
    return int(x)


def rows_of(path, need):
    """Read a CSV into a list of (line number, row dict). Stops with a plain message on any problem."""
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        sys.exit(f"{path}: cannot open it ({e.strerror})")
    with fh:
        try:
            r = csv.DictReader(fh)
            lost = [c for c in need if c not in (r.fieldnames or [])]
            if lost:
                sys.exit(f"{path}: missing columns {lost}")
            return r.fieldnames, [(n, {k: (v or "").strip() for k, v in row.items() if k}) for n, row in enumerate(r, start=2)]
        except UnicodeDecodeError:
            sys.exit(f"{path}: not UTF-8 text. Save it as CSV UTF-8 (Excel: Save as > 'CSV UTF-8')")


def iter_rows(path, need):
    """Like rows_of, but one row at a time, so a table with millions of rows (model_years.csv) needs little memory."""
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        sys.exit(f"{path}: cannot open it ({e.strerror})")
    with fh:
        try:
            r = csv.DictReader(fh)
            lost = [c for c in need if c not in (r.fieldnames or [])]
            if lost:
                sys.exit(f"{path}: missing columns {lost}")
            for n, row in enumerate(r, start=2):
                yield n, {k: (v or "").strip() for k, v in row.items() if k}
        except UnicodeDecodeError:
            sys.exit(f"{path}: not UTF-8 text. Save it as CSV UTF-8 (Excel: Save as > 'CSV UTF-8')")


def L(en, zh):
    return {"en": en, "zh": zh}


def mean(xs):
    return sum(xs) / len(xs)


def score(rep, model, period):
    """Score S over the years of `period` (docs/DATA_FORMAT.md): the years where the reported yield is usable and the
    calibrated model value exists. ratio needs 2 years, r needs 3 (and some spread on both sides)."""
    y0, y1 = period
    pairs = [(m, r) for yr, (r, ok) in rep.items() if y0 <= yr <= y1 and ok and r is not None
             for m in [model.get(yr)] if m is not None]
    n = len(pairs)
    ratio = r = None
    if n >= 2:
        mr = mean([p[1] for p in pairs])
        if mr > 0:
            ratio = round(mean([p[0] for p in pairs]) / mr, 9)   # 9 decimals: 0.8999999999999999 is 0.9, 1.1000004 stays
    ms, rs = [p[0] for p in pairs], [p[1] for p in pairs]
    if n >= 3 and max(ms) > min(ms) and max(rs) > min(rs):      # a series that never changes has no correlation
        mm, mr = mean(ms), mean(rs)
        sxy = sum((a - mm) * (b - mr) for a, b in pairs)
        sxx = sum((a - mm) ** 2 for a, _ in pairs)
        syy = sum((b - mr) ** 2 for _, b in pairs)
        if sxx > 0 and syy > 0:
            r = round(max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy))), 9)
    return {"n": n, "ratio": ratio, "r": r}


def period_mean(series, years, period):
    """Mean over the years of the period, only when every one of those years has a value."""
    if not period:
        return None
    vals = [series[years.index(y)] if y in years else None for y in range(period[0], period[1] + 1)]
    return None if any(v is None for v in vals) else keep(mean(vals))


STANDARD_VALUES = [
    {"id": "cal_yield_calibration", "name": L("Calibrated yield, calibration years", "率定后产量（率定年份）"), "unit": "t/ha",
     "kind": "num", "scale": "sequential",
     "note": L("Model yield with the unit's final settings, mean over its calibration years.",
               "使用该单元最终参数的模拟产量，率定年份平均。")},
    {"id": "cal_yield_validation", "name": L("Calibrated yield, validation years", "率定后产量（验证年份）"), "unit": "t/ha",
     "kind": "num", "scale": "sequential",
     "note": L("Model yield with the unit's final settings, mean over its validation years (not used to calibrate).",
               "使用该单元最终参数的模拟产量，验证年份平均（这些年份不参与率定）。")},
    {"id": "base_yield_calibration", "name": L("Uncalibrated yield, calibration years", "未率定产量（率定年份）"), "unit": "t/ha",
     "kind": "num", "scale": "sequential",
     "note": L("Model yield with the starting settings, mean over the unit's calibration years.",
               "使用初始参数的模拟产量，该单元率定年份平均。")},
    {"id": "base_yield_validation", "name": L("Uncalibrated yield, validation years", "未率定产量（验证年份）"), "unit": "t/ha",
     "kind": "num", "scale": "sequential",
     "note": L("Model yield with the starting settings, mean over the unit's validation years.",
               "使用初始参数的模拟产量，该单元验证年份平均。")},
    {"id": "unit_ratio_calibration", "name": L("Yield ratio, calibration years", "产量比（率定年份）"),
     "unit": "", "kind": "num", "scale": "diverging", "center": 1,
     "note": L("One value per unit: model mean ÷ reported mean. 1 = right level, 0.9 = model 10 % low.",
               "每个单元一个值：模拟均值 ÷ 统计均值。1 = 水平一致，0.9 = 模拟偏低 10%。")},
    {"id": "unit_ratio_validation", "name": L("Yield ratio, validation years", "产量比（验证年份）"),
     "unit": "", "kind": "num", "scale": "diverging", "center": 1,
     "note": L("The same over the validation years, which were not used to calibrate.",
               "验证年份的同一比值，这些年份不参与率定。")},
    {"id": "unit_r_calibration", "name": L("R, calibration years", "相关系数 R（率定年份）"), "unit": "", "kind": "num",
     "scale": "sequential",
     "note": L("One value per unit: does the model follow the good and bad years? 1 = exactly, 0 = not at all.",
               "每个单元一个值：模拟是否跟上丰年和歉年？1 = 完全一致，0 = 无关。")},
    {"id": "unit_r_validation", "name": L("R, validation years", "相关系数 R（验证年份）"), "unit": "", "kind": "num",
     "scale": "sequential",
     "note": L("The same over the validation years.", "验证年份的同一指标。")},
    {"id": "area_ha", "name": L("Crop area", "作物面积"), "unit": "ha", "kind": "num", "scale": "sequential",
     "note": L("Crop area of this water kind in the cell.", "该网格中这种水分条件下的作物面积。")},
]


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--tables", required=True, help="the folder with texts.json and the CSV tables")
    a.add_argument("--out", required=True, help="the data folder to write (the one your page is served from)")
    a.add_argument("--dry-run", action="store_true", help="check and report only; write nothing")
    a.add_argument("--allow-example", action="store_true", help=argparse.SUPPRESS)   # used by make_example_data.py
    args = a.parse_args()
    tdir, out = Path(args.tables), Path(args.out)
    notes = []
    # the lock is taken BEFORE the tables are read, so overlapping exports publish in the order they read their input
    lock = None if args.dry_run else acquire_lock(out)

    # ---- texts.json --------------------------------------------------------------------------------------------
    tp = tdir / "texts.json"
    try:
        texts = json.loads(tp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"{tp}: cannot read it as JSON ({e})")
    if not isinstance(texts, dict) or not isinstance(texts.get("page"), dict):
        sys.exit(f"{tp}: needs the 'page' part (copy the example's texts.json and change it)")
    if texts.get("example") and not args.allow_example:
        sys.exit(f"{tp}: still has \"example\": true; remove it for your real data")
    page = texts["page"]
    mu = texts.get("map_url")
    if not https_url(mu):
        sys.exit(f"{tp}: map_url must be the https address of your page (ask GeoForge if you do not have one yet)")
    g = page.get("grid_deg")
    if not isinstance(g, (int, float)) or isinstance(g, bool) or not 0 < g <= 5:
        sys.exit(f"{tp}: page.grid_deg must be the cell size in degrees, e.g. 0.1")
    yrs = page.get("years")
    if not (isinstance(yrs, list) and len(yrs) == 2 and all(isinstance(y, int) for y in yrs) and yrs[0] <= yrs[1]):
        sys.exit(f"{tp}: page.years must be [first, last], e.g. [2010, 2024]")
    YEARS = list(range(yrs[0], yrs[1] + 1))
    waters = [w.get("id") for w in page.get("water") or [] if isinstance(w, dict)]
    if not waters or len(set(waters)) != len(waters):
        sys.exit(f"{tp}: page.water must list each water kind once, e.g. [{{\"id\": \"rf\", \"name\": ...}}]")
    settings = [s.get("id") for s in page.get("settings") or [] if isinstance(s, dict)]
    if not settings or len(set(settings)) != len(settings):
        sys.exit(f"{tp}: page.settings must list each calibrated setting once, e.g. [{{\"id\": \"G2\", \"name\": ...}}]")
    cy = page.get("cell_years") or {"tile_deg": 5}
    td = cy.get("tile_deg") if isinstance(cy, dict) else None
    if not isinstance(td, int) or isinstance(td, bool) or td <= 0 or 180 % td:
        sys.exit(f"{tp}: page.cell_years.tile_deg must be a whole number that divides 180 (1, 2, 3, 5, 10, ...)")
    if "values" in page or "default_value" in page:
        notes.append("texts.json page.values / default_value are replaced by the standard values")

    def in_years(y, where):
        if not yrs[0] <= y <= yrs[1]:
            sys.exit(f"{where}: year {y} is outside page.years {yrs}")
        return y

    # ---- units.csv ---------------------------------------------------------------------------------------------
    up = tdir / "units.csv"
    _, rows = rows_of(up, ["unit_id", "name_en", "name_zh", "state", "cal_start", "cal_end", "val_start", "val_end"])
    units, order = {}, []
    for n, r in rows:
        w = f"{up} line {n}"
        uid = r["unit_id"]
        if not uid or uid in units:
            sys.exit(f"{w}: unit_id empty or repeated ('{uid}')")
        if r["state"] not in UNIT_STATES:
            sys.exit(f"{w}: state must be one of {', '.join(UNIT_STATES)} (got '{r['state']}')")
        if not r["name_en"] or not r["name_zh"]:
            sys.exit(f"{w}: name_en and name_zh must both be filled in")
        cal = [in_years(year(r["cal_start"], w + " cal_start"), w), in_years(year(r["cal_end"], w + " cal_end"), w)]
        if cal[0] > cal[1]:
            sys.exit(f"{w}: cal_start is after cal_end")
        val = None
        if r["val_start"] or r["val_end"]:
            val = [in_years(year(r["val_start"], w + " val_start"), w), in_years(year(r["val_end"], w + " val_end"), w)]
            if val[0] > val[1]:
                sys.exit(f"{w}: val_start is after val_end")
            if not (val[0] > cal[1] or val[1] < cal[0]):
                sys.exit(f"{w}: calibration and validation years overlap")
        u = {"id": uid, "name": L(r["name_en"], r["name_zh"])}
        if r.get("parent_en") or r.get("parent_zh"):
            if not (r.get("parent_en") and r.get("parent_zh")):
                sys.exit(f"{w}: parent_en and parent_zh must both be filled in, or both empty")
            u["parent"] = L(r["parent_en"], r["parent_zh"])
        u["state"] = r["state"]
        if r.get("note_en") or r.get("note_zh"):
            if not (r.get("note_en") and r.get("note_zh")):
                sys.exit(f"{w}: note_en and note_zh must both be filled in, or both empty")
            u["note"] = L(r["note_en"], r["note_zh"])
        u["periods"] = {"calibration": cal, "validation": val}
        done = whole(r.get("progress_done"), w + " progress_done")
        tot = whole(r.get("progress_total"), w + " progress_total")
        if r["state"] == "calibrating" and done is not None:
            u["progress"] = {"done": done, "what": L("rounds", "轮")}
            if tot is not None:
                u["progress"]["total"] = tot
        units[uid] = u
        order.append(uid)
    if not units:
        sys.exit(f"{up}: no units")

    # ---- cells.csv ---------------------------------------------------------------------------------------------
    cp = tdir / "cells.csv"
    _, rows = rows_of(cp, ["cell_id", "water", "lat", "lon", "unit_id", "area_ha"])
    cells, where_of, place, square = [], {}, {}, {}
    half = g / 2
    off_grid = 0
    for n, r in rows:
        w = f"{cp} line {n}"
        cid, water, uid = r["cell_id"], r["water"], r["unit_id"]
        if not cid or "|" in cid:
            sys.exit(f"{w}: cell_id empty or holds '|'")
        if water not in waters:
            sys.exit(f"{w}: water '{water}' is not in texts.json page.water")
        if uid not in units:
            sys.exit(f"{w}: unit_id '{uid}' is not in units.csv")
        if (cid, water) in where_of:
            sys.exit(f"{w}: {cid} / {water} is already on line {where_of[(cid, water)]}")
        lat, lon = num(r["lat"], w + " lat", False), num(r["lon"], w + " lon", False)
        if lat is None or lon is None or not (-90 < lat < 90 and -180 < lon < 180):
            sys.exit(f"{w}: lat/lon missing or outside the globe")
        for x in (lat, lon):
            k = x / half
            if abs(k - round(k)) > 1e-6 or round(k) % 2 == 0:
                off_grid += 1
                break
        if cid in place and place[cid][:3] != (lat, lon, uid):
            sys.exit(f"{w}: cell {cid} has another lat/lon or unit on line {place[cid][3]}")
        place.setdefault(cid, (lat, lon, uid, n))
        sq = (round(lat / half), round(lon / half))         # one grid square holds one cell id
        if square.setdefault(sq, (cid, n))[0] != cid:
            sys.exit(f"{w}: {cid} is on the same grid square as {square[sq][0]} (line {square[sq][1]}); one square "
                     f"has one cell id (its water kinds are separate rows with the same id)")
        area = num(r["area_ha"], w + " area_ha")
        if area is not None and area < 0:
            sys.exit(f"{w}: area_ha is negative")
        st = r.get("state", "")
        ustate = units[uid]["state"]
        if not st:
            st = "left_out" if ustate == "left_out" else "calibrated" if ustate == "calibrated" else "waiting"
        if st not in CELL_STATES:
            sys.exit(f"{w}: state must be one of {', '.join(CELL_STATES)} or empty (got '{st}')")
        if st == "calibrated" and ustate != "calibrated":
            sys.exit(f"{w}: the cell is 'calibrated' but its unit {uid} is '{ustate}'")
        if ustate == "calibrated" and st == "waiting":
            sys.exit(f"{w}: the cell is 'waiting' but its unit {uid} is calibrated (use calibrated, left_out or no_season)")
        if ustate == "left_out" and st != "left_out":
            sys.exit(f"{w}: the unit {uid} is left out, so its cells must be left_out too")
        where_of[(cid, water)] = n
        cells.append({"id": cid, "water": water, "lat": lat, "lon": lon, "unit": uid, "area": area,
                      "state": CELL_STATES[st], "years": {"calibrated": [None] * len(YEARS),
                                                          "uncalibrated": [None] * len(YEARS)}})
    if not cells:
        sys.exit(f"{cp}: no cells")
    if off_grid:
        sys.exit(f"{cp}: {off_grid} cell(s) are not at a cell centre of the {g}° grid (centres sit at odd multiples of "
                 f"{half}°, e.g. {half:g}, {3 * half:g}). Check grid_deg in texts.json and the lat/lon columns")
    index = {(c["id"], c["water"]): k for k, c in enumerate(cells)}

    # ---- reported.csv ------------------------------------------------------------------------------------------
    rp = tdir / "reported.csv"
    _, rows = rows_of(rp, ["unit_id", "year", "yield_t_ha"])
    rep = {uid: {} for uid in units}
    for n, r in rows:
        w = f"{rp} line {n}"
        uid = r["unit_id"]
        if uid not in units:
            sys.exit(f"{w}: unit_id '{uid}' is not in units.csv")
        y = in_years(year(r["year"], w + " year"), w)
        if y in rep[uid]:
            sys.exit(f"{w}: {uid} {y} appears twice")
        v = num(r["yield_t_ha"], w + " yield_t_ha")
        if v is not None and v < 0:
            sys.exit(f"{w}: negative yield")
        ok = (r.get("usable") or "true").lower()
        if ok not in ("true", "false", "1", "0", "yes", "no"):
            sys.exit(f"{w}: usable must be true or false (got '{r.get('usable')}')")
        rep[uid][y] = (v, ok in ("true", "1", "yes"))

    # ---- model_years.csv ---------------------------------------------------------------------------------------
    mp = tdir / "model_years.csv"
    unknown, dropped, twice, outside, no_season_vals, no_season_zero = set(), 0, set(), 0, [], 0
    if mp.exists():
        rows = iter_rows(mp, ["cell_id", "water", "which", "year", "yield_t_ha"])
        seen = {}                          # cell row -> one byte per (line, year): 1 = already written
        nyr = len(YEARS)
        for n, r in rows:
            w = f"{mp} line {n}"
            k = index.get((r["cell_id"], r["water"]))
            if k is None:
                unknown.add(f"{r['cell_id']}/{r['water']}")
                continue
            if r["which"] not in KINDS:
                sys.exit(f"{w}: which must be calibrated or uncalibrated (got '{r['which']}')")
            y = year(r["year"], w + " year")
            if not yrs[0] <= y <= yrs[1]:
                outside += 1               # e.g. spin-up years before page.years: not shown, not an error
                continue
            v = num(r["yield_t_ha"], w + " yield_t_ha")
            if v is not None and v < 0:
                sys.exit(f"{w}: negative yield")
            c = cells[k]
            if c["state"] == 3:            # no season: failed (0) or empty seasons are expected and ignored
                if v is not None and v > 0:
                    no_season_vals.append(f"line {n} ({r['cell_id']}/{r['water']} {y}: {v})")
                else:
                    no_season_zero += 1
                continue
            if c["state"] == 2 or (r["which"] == "calibrated" and units[c["unit"]]["state"] != "calibrated"):
                dropped += 1               # left-out cells, and calibrated values of units without final settings
                continue
            mark = seen.get(k)
            if mark is None:
                mark = seen[k] = bytearray(2 * nyr)
            slot = (0 if r["which"] == "calibrated" else nyr) + (y - yrs[0])
            if mark[slot]:
                twice.add((k, r["which"], y))
            mark[slot] = 1
            c["years"][r["which"]][y - yrs[0]] = None if v is None else keep(v)
        for k, which, y in twice:
            cells[k]["years"][which][y - yrs[0]] = None
    else:
        notes.append(f"{mp} not found: no model yields yet")
    if unknown:
        notes.append(f"{len(unknown)} cell/water pair(s) in model_years.csv are not in cells.csv and were skipped, "
                     f"e.g. {sorted(unknown)[:3]}")
    if dropped:
        notes.append(f"{dropped} model_years.csv row(s) skipped: left-out cells, or 'calibrated' rows of units "
                     f"that are not calibrated yet")
    if twice:
        notes.append(f"{len(twice)} cell-year(s) appear twice in model_years.csv and were left empty")
    if outside:
        notes.append(f"{outside} model_years.csv row(s) are outside page.years {yrs} and were skipped")
    if no_season_zero:
        notes.append(f"{no_season_zero} model_years.csv row(s) of no_season cells (0 or empty: no grain) were skipped")
    if no_season_vals:
        sys.exit(f"{mp}: {len(no_season_vals)} positive yield(s) for cells marked no_season in cells.csv, e.g. "
                 f"{'; '.join(no_season_vals[:3])}. A no_season cell gives no grain in any year: either the cell is "
                 f"not no_season (use calibrated or waiting) or the values are wrong")

    # ---- final_settings.csv ------------------------------------------------------------------------------------
    fp = tdir / "final_settings.csv"
    final = {}
    if fp.exists():
        head, rows = rows_of(fp, ["unit_id"] + settings)
        extra = [c for c in head if c not in settings and c != "unit_id"]
        if extra:
            notes.append(f"final_settings.csv columns {extra} are not in page.settings and were skipped")
        for n, r in rows:
            w = f"{fp} line {n}"
            uid = r["unit_id"]
            if uid not in units:
                sys.exit(f"{w}: unit_id '{uid}' is not in units.csv")
            if uid in final:
                sys.exit(f"{w}: {uid} appears twice")
            if units[uid]["state"] != "calibrated":
                notes.append(f"final_settings.csv: {uid} is not 'calibrated' in units.csv; its row was skipped")
                continue
            vals = {s: num(r[s], f"{w} {s}") for s in settings}
            if any(v is None for v in vals.values()):
                sys.exit(f"{w}: every setting needs a value")
            final[uid] = {s: (int(v) if v.is_integer() else v) for s, v in vals.items()}
    for uid in order:
        if units[uid]["state"] == "calibrated" and uid not in final:
            sys.exit(f"{fp}: unit {uid} is 'calibrated' in units.csv but has no row of final settings")

    # ---- unit model series and scores --------------------------------------------------------------------------
    by_unit = {}
    for c in cells:
        by_unit.setdefault(c["unit"], []).append(c)
    counted = lambda c: c["state"] in (0, 1) and (c["area"] or 0) > 0     # waiting or calibrated, with crop area
    no_area = [uid for uid, cs in by_unit.items() if not any(counted(c) for c in cs)
               and units[uid]["state"] != "left_out"]
    if no_area:
        notes.append(f"{len(no_area)} unit(s) have no waiting or calibrated cell with crop area, so no unit model "
                     f"yield, e.g. {no_area[:3]}")
    for uid in order:
        u, cs = units[uid], [c for c in by_unit.get(uid, []) if counted(c)]
        total = sum(c["area"] for c in cs)
        model = {"years": YEARS}
        for kind in KINDS:
            s = []
            for i in range(len(YEARS)):
                have = [(c["area"], c["years"][kind][i]) for c in cs if c["years"][kind][i] is not None]
                a_have = sum(x[0] for x in have)
                s.append(keep(sum(x * y for x, y in have) / a_have) if covered_enough(a_have, total) else None)
            model[kind] = s
        ry = sorted(rep[uid])
        u["reported"] = {"years": ry, "yield": [rep[uid][y][0] for y in ry], "usable": [rep[uid][y][1] for y in ry]}
        u["model"] = model
        if u["state"] == "calibrated":
            m = {y: v for y, v in zip(YEARS, model["calibrated"])}
            per = u["periods"]
            u["final"] = {"settings": final[uid], "scores": {
                "calibration": score(rep[uid], m, per["calibration"]),
                "validation": score(rep[uid], m, per["validation"]) if per["validation"] else None}}
        else:
            u["final"] = None
        if "progress" in u:            # keep the spec's field order: progress last
            u["progress"] = u.pop("progress")

    # ---- cells.json columns ------------------------------------------------------------------------------------
    vals = {v["id"]: [] for v in STANDARD_VALUES}
    for c in cells:
        u = units[c["unit"]]
        per = u["periods"]
        sc = (u["final"] or {}).get("scores") or {}
        out_cell = c["state"] == 2
        vals["area_ha"].append(c["area"])
        for kind, pre in (("calibrated", "cal"), ("uncalibrated", "base")):
            for part, p in (("calibration", per["calibration"]), ("validation", per["validation"])):
                vals[f"{pre}_yield_{part}"].append(None if out_cell else period_mean(c["years"][kind], YEARS, p))
        for part in ("calibration", "validation"):
            s = sc.get(part) or {}
            vals[f"unit_ratio_{part}"].append(s.get("ratio"))       # the unit's score, on every one of its cells
            vals[f"unit_r_{part}"].append(s.get("r"))
    cells_json = {"id": [c["id"] for c in cells], "water": [c["water"] for c in cells],
                  "lat": [c["lat"] for c in cells], "lon": [c["lon"] for c in cells],
                  "unit": [c["unit"] for c in cells], "area_ha": [c["area"] for c in cells],
                  "state": [c["state"] for c in cells], "values": vals}

    # ---- cell_years tiles --------------------------------------------------------------------------------------
    tiles = {}                      # one file for every square that holds a cell, even with no yearly values yet
    for c in cells:
        name = f"{math.floor(c['lat'] / td) * td}_{math.floor(c['lon'] / td) * td}"
        t = tiles.setdefault(name, {"years": YEARS, "cells": {}})
        rec = {k: c["years"][k] for k in KINDS if any(v is not None for v in c["years"][k])}
        if rec:
            t["cells"][f"{c['id']}|{c['water']}"] = rec

    # ---- manifest ----------------------------------------------------------------------------------------------
    manifest = {k: v for k, v in texts.items() if k not in ("page", "updated_at", "data_version")}
    manifest["feed_version"] = 1
    n_cal = sum(1 for u in units.values() if u["state"] == "calibrated")
    if manifest.get("facts") == "auto":
        n_cells = len(place)
        manifest["facts"] = [
            L(f"{n_cal} of {len(units)} units calibrated", f"已率定 {n_cal}/{len(units)} 个单元"),
            L(f"{n_cells:,} grid cells", f"{n_cells:,} 个网格"),
            L(f"years {yrs[0]}–{yrs[1]}", f"{yrs[0]}–{yrs[1]} 年")]
    newpage = {k: v for k, v in page.items() if k not in ("values", "default_value", "cell_years")}
    newpage["values"] = STANDARD_VALUES
    newpage["default_value"] = "cal_yield_calibration"
    newpage["cell_years"] = {"tile_deg": td}
    manifest["page"] = newpage
    first = ["feed_version", "project_id", "example", "updated_at", "data_version"]
    units_json = {"units": [units[u] for u in order]}

    for x in notes:
        print("note:", x, file=sys.stderr)
    summary = (f"{len(units)} units ({n_cal} calibrated), {len(cells)} cell rows ({len(place)} cells), "
               f"{sum(len(t['cells']) for t in tiles.values())} with yearly yields in {len(tiles)} year file(s)")
    # the manifest must pass the same feed and page checks as check_data.py before anything is published,
    # so a mistake in texts.json (e.g. no runs) never reaches the page
    import check_data as cd
    cd.ERR.clear(); cd.WARN.clear()
    cd.check_feed({**manifest, "updated_at": "2000-01-01T00:00:00+00:00", "data_version": "pending"}, args.allow_example)
    cd.check_page(newpage)
    if cd.ERR:
        sys.exit("texts.json has problems, nothing written:\n  " + "\n  ".join(cd.ERR))
    if args.dry_run:
        print(f"dry run, nothing written: {summary}")
        return

    try:
        publish(out, manifest, cells_json, units_json, tiles, first, summary)
    finally:
        if lock is not None:
            lock.close()


def acquire_lock(out):
    """Hold data/.export.lock for the whole export: a second export into the same folder waits for the first."""
    out.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
        return None
    fh = open(out / ".export.lock", "a")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("note: another export into this folder is running; waiting for it", file=sys.stderr)
        fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def valid_current(out, man):
    """The data_version of the current export, or None when the manifest or its folder is not complete."""
    if not isinstance(man, dict):
        return None
    ver = man.get("data_version")
    if not (isinstance(ver, str) and VERSION_RE.match(ver) and parse_time(man.get("updated_at")) is not None):
        return None
    vdir = out / "v" / ver
    if not ((vdir / "cells.json").is_file() and (vdir / "units.json").is_file() and (vdir / "cell_years").is_dir()):
        return None
    return ver


def publish(out, manifest, cells_json, units_json, tiles, first, summary):
    # ---- the current export, if any -----------------------------------------------------------------------------
    old_man = read_json(out / "manifest.json")
    old_ver = valid_current(out, old_man)
    for flat in ("cells.json", "units.json", "cell_years"):
        if (out / flat).exists():
            print(f"note: {out / flat} is from the older layout and is no longer read; you may delete it",
                  file=sys.stderr)
    if old_ver and same_export(out / "v" / old_ver, old_man, manifest, cells_json, units_json, tiles):
        print(f"nothing changed since data_version {old_ver}: nothing written ({summary})")
        return

    # ---- a new version: folder first (its name reserved by mkdir), manifest last ------------------------------------
    now = datetime.now(timezone.utc).replace(microsecond=0)
    prev = parse_time(old_man.get("updated_at")) if isinstance(old_man, dict) else None
    if prev is not None and now <= prev:
        now = prev + timedelta(seconds=1)              # updated_at always moves forward
    (out / "v").mkdir(parents=True, exist_ok=True)
    base = now.strftime("%Y%m%dT%H%M%SZ")
    ver, k = base, 2
    while True:
        try:
            if ver == old_ver:
                raise FileExistsError
            os.mkdir(out / "v" / ver)
            break
        except FileExistsError:
            ver = f"{base}_{k}"
            k += 1
    vdir = out / "v" / ver
    for name, t in tiles.items():
        write(vdir / "cell_years" / f"{name}.json", t)
    (vdir / "cell_years").mkdir(exist_ok=True)
    write(vdir / "units.json", units_json)
    write(vdir / "cells.json", cells_json)
    manifest["updated_at"] = now.isoformat()
    manifest["data_version"] = ver
    manifest = {**{k: manifest[k] for k in first if k in manifest}, **{k: v for k, v in manifest.items() if k not in first}}
    write(out / "manifest.json", manifest)

    # ---- history: when each version stopped being current -------------------------------------------------------
    hp = out / "v" / ".history.json"
    hist = read_json(hp)
    hist = [h for h in hist if isinstance(h, dict) and isinstance(h.get("version"), str)] if isinstance(hist, list) else []
    stamp = now.isoformat()
    for h in hist:
        if h.get("current_until") is None and h["version"] != ver:
            h["current_until"] = stamp
    if old_ver and not any(h["version"] == old_ver for h in hist):   # retired now, even without an earlier entry
        hist.append({"version": old_ver, "current_from": None, "current_until": stamp})
    hist.append({"version": ver, "current_from": stamp, "current_until": None})

    # ---- remove old versions: keep this one, the one before, and any current less than 30 minutes ago -------------
    gone = 0
    until = {h["version"]: parse_time(h.get("current_until")) for h in hist}
    for d in (out / "v").iterdir():
        if not d.is_dir() or d.is_symlink() or not VERSION_RE.match(d.name) or d.name in (ver, old_ver):
            continue
        t = until.get(d.name)
        if t is not None:
            if (now - t).total_seconds() < KEEP_S:
                continue
        elif time.time() - d.stat().st_mtime < KEEP_S:     # no history (older kit): its folder time
            continue
        shutil.rmtree(d)
        gone += 1
    names = {d.name for d in (out / "v").iterdir() if d.is_dir()}
    write(hp, [h for h in hist if h["version"] in names][-200:])
    print(f"written to {vdir} (data_version {ver}{', ' + str(gone) + ' old version(s) removed' if gone else ''}): "
          f"{summary}. Next: python3 tools/check_data.py {out}")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def parse_time(text):
    try:
        t = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return t if t.tzinfo else None


def same_export(vdir, old_man, manifest, cells_json, units_json, tiles):
    """True when the new export would be the same as the one in vdir (the manifest compared without its times)."""
    # compared as JSON text with sorted keys, so types count too (true is not 1, 1.0 is not 1)
    canon = lambda o: json.dumps(o, sort_keys=True, ensure_ascii=False, allow_nan=False)
    strip = lambda m: {k: v for k, v in m.items() if k not in ("updated_at", "data_version")}
    try:
        return _same(vdir, canon, strip, old_man, manifest, cells_json, units_json, tiles)
    except ValueError:                  # e.g. a hand-written NaN in the old files: treat as changed and write anew
        return False


def _same(vdir, canon, strip, old_man, manifest, cells_json, units_json, tiles):
    if canon(strip(old_man)) != canon(strip(manifest)):
        return False
    for name, obj in (("units.json", units_json), ("cells.json", cells_json)):
        old = read_json(vdir / name)
        if old is None or canon(old) != canon(obj):
            return False
    tdir = vdir / "cell_years"
    names = {p.stem for p in tdir.glob("*.json")} if tdir.is_dir() else set()
    if names != set(tiles):
        return False
    for n, t in tiles.items():
        old = read_json(tdir / f"{n}.json")
        if old is None or canon(old) != canon(t):
            return False
    return True


if __name__ == "__main__":
    main()
