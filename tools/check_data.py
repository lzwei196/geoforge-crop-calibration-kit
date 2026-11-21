#!/usr/bin/env python3
"""Check a data folder against docs/DATA_FORMAT.md before you publish it.

    python3 tools/check_data.py app/public/data        # or the folder your web server serves

It reads manifest.json and the export folder it names (v/<data_version>/: cells.json, units.json, cell_years/).

It checks every file and field, and it works out the numbers again from the files themselves (each unit's model
yield from its cells, the scores, each cell's period means) and compares them with what is written, so a page
never shows a score that does not follow from its own data.
Prints every problem it finds. Exit code 0 = ready to publish, 1 = errors (fix them first).
--allow-example accepts the example data (for trying the kit only). Only the Python standard library is used.
"""
import json
import math
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ERR, WARN = [], []
ID = re.compile(r"^[a-z0-9-]{1,64}$")
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VERSION = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUSES = {"running", "paused", "stopped", "finished", "failed"}
UNIT_STATES = {"waiting", "calibrating", "calibrated", "left_out"}
KINDS = ("calibrated", "uncalibrated")
COVER = 0.9
TOL_SCORE = 1e-6        # scores are recomputed from units.json exactly (ratio)
TOL_R = 1e-5            # r is worked out with another formula here, so allow a little more
TOL_MEAN = 1e-5         # unit yields and cell means are written with 6 decimals (t/ha)
BAD = object()          # load(): the file is missing or unreadable (the error is already recorded)
STANDARD = ("cal_yield_calibration", "cal_yield_validation", "base_yield_calibration", "base_yield_validation",
            "unit_ratio_calibration", "unit_ratio_validation", "unit_r_calibration", "unit_r_validation", "area_ha")


def err(where, msg): ERR.append(f"{where}: {msg}")
def warn(where, msg): WARN.append(f"{where}: {msg}")


def no_nan(name):
    raise ValueError(f"{name} is not allowed in JSON (browsers cannot read the file); write null")


def load(p, max_mb=None, label=None, want=dict):
    """The parsed file, or BAD (error recorded). A file that parses but is not a JSON object is an error too."""
    label = label or p.name
    if not p.is_file():
        err(label, "missing"); return BAD
    if max_mb and p.stat().st_size > max_mb * 1024 * 1024:
        warn(label, f"larger than {max_mb} MB: slow to load for readers far away; ask GeoForge how to split it")
    try:
        v = json.loads(p.read_text(encoding="utf-8"), parse_constant=no_nan)
    except Exception as e:                      # noqa: BLE001 - report any read problem
        err(label, f"not valid UTF-8 JSON ({e})"); return BAD
    if want is not None and not isinstance(v, want):
        err(label, "must be a JSON object {...}"); return BAD
    return v


def isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def num_or_null(x):
    return x is None or isnum(x)


def isint(x):
    return isinstance(x, int) and not isinstance(x, bool)


def as_dict(where, v):
    if isinstance(v, dict):
        return v
    err(where, "must be an object {...}")
    return {}


def as_list(where, v):
    """A list, or [] (error recorded) for anything else; None counts as an empty list."""
    if v is None or isinstance(v, list):
        return v or []
    err(where, "must be a list [...]")
    return []


def https_url(u):
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


def text2(where, v, maxlen=None, need=True):
    """{"en": "...", "zh": "..."}: both languages, not empty, not too long."""
    if v is None and not need:
        return
    if not isinstance(v, dict):
        return err(where, 'must be {"en": "...", "zh": "..."}')
    for lang in ("en", "zh"):
        s = v.get(lang)
        if not isinstance(s, str) or not s.strip():
            err(where, f'"{lang}" text missing')
        elif maxlen and len(s) > maxlen:
            err(where, f'"{lang}" text longer than {maxlen} characters')
        elif re.search(r"<[a-zA-Z/]", s):
            warn(where, f'"{lang}" looks like HTML; it is shown as plain text')


def utc_time(where, s):
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return err(where, f"not a time like 2026-10-22T03:07:15+00:00: {s!r}")
    if t.tzinfo is None:
        return err(where, "time has no zone; write UTC with +00:00")
    return t


def is_day(s):
    try:
        return bool(DAY.match(s)) and date.fromisoformat(s) is not None
    except (TypeError, ValueError):
        return False


def close(a, b, tol):
    if a is None or b is None:
        return a is None and b is None
    return isnum(a) and isnum(b) and abs(a - b) <= tol


def mean(xs):
    return sum(xs) / len(xs)


def score(rep, model, period):
    """The rule of docs/DATA_FORMAT.md, written independently of csv_to_data.py (two passes with math.fsum, over
    lists built year by year), so a mistake in one is not simply repeated in the other."""
    y0, y1 = period
    xs, ys = [], []
    for y in range(y0, y1 + 1):
        r, ok = rep.get(y, (None, False))
        m = model.get(y)
        if ok is True and isnum(r) and isnum(m):
            xs.append(m); ys.append(r)
    n = len(xs)
    ratio = r = None
    if n >= 2 and sum(ys) > 0:
        ratio = sum(xs) / sum(ys)
    if n >= 3 and len(set(xs)) > 1 and len(set(ys)) > 1:      # a series that never changes has no correlation
        mx, my = math.fsum(xs) / n, math.fsum(ys) / n           # pass 1: means; pass 2: centred sums
        dx, dy = [a - mx for a in xs], [b - my for b in ys]
        cov = math.fsum(a * b for a, b in zip(dx, dy))
        vx, vy = math.fsum(a * a for a in dx), math.fsum(b * b for b in dy)
        if vx > 0 and vy > 0:
            r = max(-1.0, min(1.0, cov / (math.sqrt(vx) * math.sqrt(vy))))
    return {"n": n, "ratio": ratio, "r": r}


def covered_enough(have, total):
    """The 90 % rule of docs/DATA_FORMAT.md, with room for rounding."""
    return total > 0 and have > 0 and have >= COVER * total - 1e-9 * total


def check_feed(m, allow_example):
    if m.get("feed_version") != 1:
        err("manifest", "feed_version must be 1")
    if not ID.match(str(m.get("project_id", ""))):
        err("manifest", "project_id: a-z, 0-9 and '-' only, at most 64")
    if m.get("example") and not allow_example:
        err("manifest", '"example": true - this is example data; remove the flag only when the data are real')
    utc_time("manifest.updated_at", m.get("updated_at"))
    if not VERSION.match(str(m.get("data_version", ""))):
        err("manifest.data_version", "the export folder name under v/ (A-Z a-z 0-9 _ -); run csv_to_data.py")
    text2("manifest.group", m.get("group"), 80)
    text2("manifest.title", m.get("title"), 80)
    text2("manifest.text", m.get("text"), 400)
    tags = as_dict("manifest.tags", m.get("tags"))
    for lang in ("en", "zh"):
        t = tags.get(lang)
        if not isinstance(t, list) or not 1 <= len(t) <= 6 or not all(isinstance(x, str) and x.strip() for x in t):
            err("manifest.tags", f'"{lang}": a list of 1 to 6 short text labels')
    facts = m.get("facts") or []
    if not isinstance(facts, list) or len(facts) > 4:
        err("manifest.facts", "a list of at most 4 texts"); facts = []
    for k, f in enumerate(facts):
        text2(f"manifest.facts[{k}]", f, 40)
    if not https_url(m.get("map_url")):
        err("manifest.map_url", "required: the https:// address of your page, with its host name")
    runs = m.get("runs")
    if not isinstance(runs, list) or not runs:
        err("manifest.runs", "at least one run")
        runs = []
    seen = set()
    for k, r in enumerate(runs):
        r = as_dict(f"manifest.runs[{k}]", r)
        rid = r.get("run_id")
        if not isinstance(rid, str) or not RUN_ID.match(rid) or rid in seen:      # text, not a number
            err(f"manifest.runs[{k}]", "run_id: A-Z a-z 0-9 _ -, unique")
        seen.add(rid)
        text2(f"manifest.runs[{k}].name", r.get("name"), 80)
        if not is_day(r.get("started")):
            err(f"manifest.runs[{k}].started", "date YYYY-MM-DD")
    return [r for r in runs if isinstance(r, dict)]


def check_page(p):
    """Returns what the later checks need, or None when the page part is too broken to go on."""
    for k, n in (("crop", 40), ("model", 80), ("region", 80), ("method", 400), ("reported_source", 160), ("unit_word", 30)):
        text2(f"page.{k}", p.get(k), n)
    g = p.get("grid_deg")
    if not isnum(g) or not 0 < g <= 5:
        err("page.grid_deg", "the cell size in degrees, e.g. 0.1"); g = None
    yrs = p.get("years")
    if not (isinstance(yrs, list) and len(yrs) == 2 and all(isint(y) for y in yrs) and yrs[0] <= yrs[1]):
        err("page.years", "[first, last], e.g. [2010, 2024]"); yrs = None
    waters = [as_dict("page.water", w) for w in as_list("page.water", p.get("water"))]
    wids = [w.get("id") for w in waters]
    if not wids or not all(isinstance(x, str) and x and "|" not in x for x in wids) or len(set(map(str, wids))) != len(wids):
        err("page.water", "at least one water kind, ids unique text, no '|'")
    wids = [x for x in wids if isinstance(x, str)]
    for w in waters:
        text2(f"page.water[{w.get('id')}].name", w.get("name"), 30)
    sdefs = [as_dict("page.settings", s) for s in as_list("page.settings", p.get("settings"))]
    sids = [s.get("id") for s in sdefs]
    if not sids or not all(isinstance(x, str) and x for x in sids) or len(set(map(str, sids))) != len(sids):
        err("page.settings", "at least one setting, ids unique text")
    sids = [x for x in sids if isinstance(x, str)]
    for s in sdefs:
        text2(f"page.settings[{s.get('id')}].name", s.get("name"), 60, need=False)
        text2(f"page.settings[{s.get('id')}].note", s.get("note"), 160, need=False)
        if "unit" in s and not isinstance(s["unit"], str):
            err(f"page.settings[{s.get('id')}].unit", "text")
    vdefs = [as_dict("page.values", v) for v in as_list("page.values", p.get("values"))]
    vids = [v.get("id") for v in vdefs]
    if not vdefs or not all(isinstance(x, str) and x for x in vids) or len(set(map(str, vids))) != len(vids):
        err("page.values", "at least one value, ids unique text")
    vids = [x for x in vids if isinstance(x, str)]
    lost = [x for x in STANDARD if x not in vids]
    if lost:
        err("page.values", f"the nine standard values are all needed (csv_to_data.py writes them); missing {lost}")
    for v in vdefs:
        w = f"page.values[{v.get('id')}]"
        text2(w + ".name", v.get("name"), 40)
        text2(w + ".note", v.get("note"), 160, need=False)
        if v.get("kind") != "num":
            err(w, 'kind must be "num"')
        if not isinstance(v.get("unit", ""), str):
            err(w + ".unit", "text")
        if v.get("scale") not in (None, "diverging", "sequential"):
            err(w, 'scale must be "diverging" or "sequential"')
        if "center" in v and not isnum(v["center"]):
            err(w + ".center", "a number")
    if p.get("default_value") not in vids:
        err("page.default_value", "must be one of the value ids")
    cy = as_dict("page.cell_years", p.get("cell_years"))
    td = cy.get("tile_deg")
    if not (isint(td) and td > 0 and 180 % td == 0):
        err("page.cell_years.tile_deg", "a whole number that divides 180, e.g. 5"); td = None
    if g is None or yrs is None or td is None:
        return None
    return {"g": g, "years": yrs, "waters": set(wids), "settings": sids,
            "values": list(dict.fromkeys(vids + list(STANDARD))), "td": td}


def check_units(us, P):
    """units.json -> {id: unit} of the well-formed units."""
    y0, y1 = P["years"]
    if not isinstance(us, dict) or not isinstance(us.get("units"), list):
        if us is not BAD:
            err("units.json", 'must be {"units": [...]}')
        return {}
    if not us["units"]:
        err("units.json", "no units"); return {}
    out = {}
    for k, u in enumerate(us["units"]):
        u = as_dict(f"units[{k}]", u)
        uid = u.get("id")
        w = f"units[{uid}]"
        if not isinstance(uid, str) or not uid or uid in out:
            err(f"units[{k}]", f"id empty or repeated: {uid!r}"); continue
        text2(w + ".name", u.get("name"), 80)
        text2(w + ".parent", u.get("parent"), 80, need=False)
        text2(w + ".note", u.get("note"), 200, need=False)
        st = u.get("state")
        if not isinstance(st, str) or st not in UNIT_STATES:
            err(w + ".state", f"one of {sorted(UNIT_STATES)}")
        per = as_dict(w + ".periods", u.get("periods"))
        cal, val = per.get("calibration"), per.get("validation")
        ok_per = True
        for name, pr, need in (("calibration", cal, True), ("validation", val, False)):
            if pr is None and not need:
                continue
            if not (isinstance(pr, list) and len(pr) == 2 and all(isint(x) for x in pr) and y0 <= pr[0] <= pr[1] <= y1):
                err(f"{w}.periods.{name}", f"[first, last] inside page.years {P['years']}"); ok_per = False
        if ok_per and val and not (val[0] > cal[1] or val[1] < cal[0]):
            err(w + ".periods", "calibration and validation years overlap")
        rep = as_dict(w + ".reported", u.get("reported"))
        ry, rv, ru = rep.get("years"), rep.get("yield"), rep.get("usable")
        rmap = {}
        if not (isinstance(ry, list) and isinstance(rv, list) and isinstance(ru, list) and len(ry) == len(rv) == len(ru)):
            err(w + ".reported", '"years", "yield", "usable": lists of the same length')
        else:
            if not all(isint(y) and y0 <= y <= y1 for y in ry) or ry != sorted(set(ry)):
                err(w + ".reported.years", "whole years inside page.years, each once, oldest first")
            if not all(num_or_null(x) and (x is None or x >= 0) for x in rv):
                err(w + ".reported.yield", "numbers >= 0 (t/ha) or null")
            if not all(isinstance(x, bool) for x in ru):
                err(w + ".reported.usable", "true or false")
            # only well-formed entries take part in the sums (bad ones are reported above)
            rmap = {y: (v if isnum(v) and v >= 0 else None, ok is True) for y, v, ok in zip(ry, rv, ru) if isint(y)}
        mo = as_dict(w + ".model", u.get("model"))
        my = mo.get("years")
        mmap = {k2: {} for k2 in KINDS}
        if my != list(range(y0, y1 + 1)):
            err(w + ".model.years", f"must be every year of page.years ({y0}-{y1})"); my = None
        else:
            for kind in KINDS:
                s = mo.get(kind)
                if not isinstance(s, list) or len(s) != len(my) or not all(num_or_null(x) and (x is None or x >= 0) for x in s):
                    err(f"{w}.model.{kind}", f"a list of {len(my)} numbers >= 0 or null")
                else:
                    mmap[kind] = dict(zip(my, s))
        fin = u.get("final")
        if st == "calibrated":
            if not isinstance(fin, dict):
                err(w + ".final", "a calibrated unit needs its final settings and scores")
            else:
                sv = as_dict(w + ".final.settings", fin.get("settings"))
                if set(sv) != set(P["settings"]) or not all(isnum(x) for x in sv.values()):
                    err(w + ".final.settings", f"one number for each of {P['settings']}")
                sc = as_dict(w + ".final.scores", fin.get("scores"))
                if ok_per and my is not None:
                    for part, pr in (("calibration", cal), ("validation", val)):
                        got = sc.get(part)
                        if pr is None:
                            if got is not None:
                                err(f"{w}.final.scores.{part}", "must be null: the unit has no validation years")
                            continue
                        if not isinstance(got, dict) or not all(k3 in got for k3 in ("n", "ratio", "r")) \
                                or not isint(got.get("n")) or not num_or_null(got.get("ratio")) or not num_or_null(got.get("r")):
                            err(f"{w}.final.scores.{part}", '{"n": whole number, "ratio": number or null, "r": number or null}')
                            continue
                        want = score(rmap, mmap["calibrated"], pr)
                        if got["n"] != want["n"] or not close(got["ratio"], want["ratio"], TOL_SCORE) \
                                or not close(got["r"], want["r"], TOL_R):
                            err(f"{w}.final.scores.{part}", f"does not follow from reported + model: written {got}, "
                                                            f"worked out n={want['n']} ratio={want['ratio']} r={want['r']}")
        elif fin is not None:
            err(w + ".final", f"must be null while the unit is '{st}'")
        if st != "calibrated" and any(v is not None for v in mmap["calibrated"].values()):
            err(w + ".model.calibrated", f"must be all null while the unit is '{st}'")
        pg = u.get("progress")
        if pg is not None:
            if not isinstance(pg, dict) or not isint(pg.get("done")) or not (pg.get("total") is None or isint(pg.get("total"))):
                err(w + ".progress", '{"done": n, "total": n, "what": {"en", "zh"}}')
            else:
                text2(w + ".progress.what", pg.get("what"), 30)
        u["_rep"], u["_model"], u["_cal"], u["_val"] = rmap, mmap, cal if ok_per else None, val if ok_per else None
        out[uid] = u
    return out


def check_cells(c, P, units):
    """cells.json -> list of rows (dicts) of the well-formed cells."""
    if not isinstance(c, dict):
        if c is not BAD:
            err("cells.json", "must be an object of columns")
        return []
    ids = c.get("id")
    if not isinstance(ids, list):
        err("cells.json", '"id" must be a list'); return []
    n = len(ids)
    cols = ("id", "water", "lat", "lon", "unit", "area_ha", "state")
    bad = [k for k in cols if not isinstance(c.get(k), list) or len(c[k]) != n]
    if bad:
        err("cells.json", f'columns {bad} must be lists as long as "id" ({n})'); return []
    if not n:
        err("cells.json", "no cells"); return []
    half = P["g"] / 2
    rows, seen, place, off, square = [], set(), {}, 0, {}
    for i in range(n):
        cid, wa, la, lo, uid, ar, st = (c[k][i] for k in cols)
        w = f"cells row {i} ({cid}/{wa})"
        if not isinstance(cid, str) or not cid or "|" in cid:
            err(w, "id must be text without '|'"); continue
        if not isinstance(wa, str) or not isinstance(uid, str):
            err(w, "water and unit must be text"); continue
        if (cid, wa) in seen:
            err(w, "the same cell and water kind twice"); continue
        seen.add((cid, wa))
        if wa not in P["waters"]:
            err(w, f"water '{wa}' is not in page.water")
        if uid not in units:
            err(w, f"unit '{uid}' is not in units.json"); continue
        if not (isnum(la) and isnum(lo) and -90 < la < 90 and -180 < lo < 180):
            err(w, "lat/lon out of range"); continue
        for x in (la, lo):
            k = x / half
            if abs(k - round(k)) > 1e-6 or round(k) % 2 == 0:
                off += 1
                break
        if cid in place and place[cid] != (la, lo, uid):
            err(w, "the same cell id with another lat/lon or unit")
        place.setdefault(cid, (la, lo, uid))
        sq = (round(la / half), round(lo / half))
        if square.setdefault(sq, cid) != cid:
            err(w, f"on the same grid square as cell {square[sq]}: one square has one cell id")
        if not (ar is None or (isnum(ar) and ar >= 0)):
            err(w, "area_ha must be a number >= 0 or null"); ar = None
        if st not in (0, 1, 2, 3) or isinstance(st, bool):
            err(w, "state must be 0, 1, 2 or 3"); continue
        ust = units[uid].get("state")
        if st == 1 and ust != "calibrated":
            err(w, f"state 1 (calibrated) but its unit is '{ust}'")
        if ust == "calibrated" and st == 0:
            err(w, "state 0 (waiting) but its unit is calibrated")
        if ust == "left_out" and st != 2:
            err(w, "its unit is left out, so the cell must be state 2")
        rows.append({"i": i, "id": cid, "water": wa, "lat": la, "lon": lo, "unit": uid, "area": ar, "state": st})
    if off:
        err("cells.json", f"{off} cell(s) are not at a cell centre of the {P['g']}° grid (odd multiples of {half:g}°)")
    vals = as_dict("cells.values", c.get("values"))
    for vid in P["values"]:
        col = vals.get(vid)
        if not isinstance(col, list) or len(col) != n:
            err("cells.values", f'"{vid}" must be a list of {n} numbers or null'); continue
        b = [i for i, x in enumerate(col) if not num_or_null(x)]
        if b:
            err("cells.values", f'"{vid}": {len(b)} entries are not numbers or null, first at row {b[0]}')
    return rows


def check_tiles(root, P, rows, units):
    """cell_years/ -> {"id|water": {kind: {year: value}}}."""
    td, (y0, y1) = P["td"], P["years"]
    by_key = {f"{r['id']}|{r['water']}": r for r in rows}
    got = {}
    d = root / "cell_years"
    need = {f"{math.floor(r['lat'] / td) * td}_{math.floor(r['lon'] / td) * td}" for r in rows}
    have = {tp.stem for tp in d.glob("*.json")} if d.is_dir() else set()
    lost = sorted(need - have)
    if lost:
        err("cell_years", f"{len(lost)} square(s) hold cells but have no file (write one even with no values), "
                          f"e.g. {lost[0]}.json")
    for x in sorted(have - need):
        err(f"cell_years/{x}.json", "no cell in this square: a file left from an older export?")
    for tp in sorted(d.glob("*.json")) if d.is_dir() else []:
        t = load(tp, 20, label=f"cell_years/{tp.name}")
        if t is BAD:
            continue
        if not isinstance(t.get("cells"), dict):
            err(f"cell_years/{tp.name}", '{"years": [...], "cells": {...}}')
            continue
        ys = t.get("years")
        if not (isinstance(ys, list) and ys and all(isint(y) and y0 <= y <= y1 for y in ys) and ys == sorted(set(ys))):
            err(f"cell_years/{tp.name}.years", "whole years inside page.years, each once, oldest first"); continue
        for key, rec in t["cells"].items():
            w = f"cell_years/{tp.name}[{key}]"
            r = by_key.get(key)
            if r is None:
                err(w, "no such cell|water in cells.json"); continue
            want = f"{math.floor(r['lat'] / td) * td}_{math.floor(r['lon'] / td) * td}"
            if tp.stem != want:
                err(w, f"belongs in cell_years/{want}.json")
            if key in got:
                err(w, "this cell is in two year files"); continue
            if not isinstance(rec, dict) or set(rec) - set(KINDS):
                err(w, '{"calibrated": [...], "uncalibrated": [...]}'); continue
            out = {}
            for kind, s in rec.items():
                if not isinstance(s, list) or len(s) != len(ys) or not all(num_or_null(x) and (x is None or x >= 0) for x in s):
                    err(f"{w}.{kind}", f"a list of {len(ys)} numbers >= 0 (t/ha) or null"); continue
                out[kind] = dict(zip(ys, s))
            if r["state"] == 3:
                err(w, "the cell has no season (state 3), so it must have no entry in the year files")
            elif r["state"] == 2 and any(v is not None for s in out.values() for v in s.values()):
                err(w, "the cell is left out (state 2), so it must have no yearly yields")
            if units[r["unit"]].get("state") != "calibrated" and any(v is not None for v in out.get("calibrated", {}).values()):
                err(w, "calibrated yields, but the cell's unit is not calibrated")
            got[key] = out
    return got


def check_numbers(c, P, units, rows, years_of):
    """Work the numbers out again from the files and compare with what is written."""
    y0, y1 = P["years"]
    vals = c.get("values") if isinstance(c.get("values"), dict) else {}
    # every cell that shows a yield on the map must have its yearly yields
    shown = [v for v in ("cal_yield_calibration", "cal_yield_validation", "base_yield_calibration", "base_yield_validation")
             if isinstance(vals.get(v), list) and len(vals[v]) == len(c["id"])]
    miss = [r for r in rows if f"{r['id']}|{r['water']}" not in years_of and any(vals[v][r["i"]] is not None for v in shown)]
    if miss:
        err("cell_years", f"{len(miss)} cell(s) show a yield on the map but have no yearly yields, e.g. "
                          f"{miss[0]['id']}|{miss[0]['water']}")
    # cell period means and unit values copied to cells
    bad = {}
    for r in rows:
        u = units[r["unit"]]
        ys = years_of.get(f"{r['id']}|{r['water']}", {})
        fin = u.get("final") if isinstance(u.get("final"), dict) else {}
        sc = fin.get("scores") if isinstance(fin.get("scores"), dict) else {}
        for vid in vals:
            col = vals[vid]
            if not isinstance(col, list) or len(col) != len(c["id"]):
                continue
            x = col[r["i"]]
            want, tol = "skip", TOL_MEAN
            m = re.match(r"^(cal|base)_yield_(calibration|validation)$", vid)
            if m and r["state"] == 2:
                want = None                              # left out: no yields (but area and unit scores are shown)
            elif m:
                kind = "calibrated" if m.group(1) == "cal" else "uncalibrated"
                pr = u["_cal"] if m.group(2) == "calibration" else u["_val"]
                s = ys.get(kind, {})
                v = [s.get(y) for y in range(pr[0], pr[1] + 1)] if pr else [None]
                want = None if any(e is None for e in v) else mean(v)
            elif re.match(r"^unit_(ratio|r)_(calibration|validation)$", vid):
                _, what, part = vid.split("_")
                sp = sc.get(part) if isinstance(sc.get(part), dict) else {}
                want, tol = sp.get(what), 1e-9
            elif vid == "area_ha":
                want, tol = r["area"], 1e-9
            if want != "skip" and not close(x, want, tol):
                bad.setdefault(vid, (0, r, x, want))
                bad[vid] = (bad[vid][0] + 1,) + bad[vid][1:]
    for vid, (k, r, x, want) in bad.items():
        err(f"cells.values.{vid}", f"{k} cell(s) do not follow from the yearly yields / unit scores, e.g. "
                                   f"{r['id']}|{r['water']}: written {x}, worked out {want}")
    # each unit's model yield from its cells (area-weighted, 90 % cover; only waiting/calibrated cells with area count)
    by_unit = {}
    for r in rows:
        if r["state"] in (0, 1) and isnum(r["area"]) and r["area"] > 0:
            by_unit.setdefault(r["unit"], []).append(r)
    for uid, u in units.items():
        cs = by_unit.get(uid, [])
        total = sum(r["area"] for r in cs)
        for kind in KINDS:
            wrong = []
            for y, x in u["_model"][kind].items():
                have = [(r["area"], years_of.get(f"{r['id']}|{r['water']}", {}).get(kind, {}).get(y)) for r in cs]
                have = [h for h in have if h[1] is not None]
                a = sum(h[0] for h in have)
                want = sum(h[0] * h[1] for h in have) / a if covered_enough(a, total) else None
                if not close(x, want, TOL_MEAN):
                    wrong.append((y, x, want))
            if wrong:
                y, x, want = wrong[0]
                err(f"units[{uid}].model.{kind}", f"{len(wrong)} year(s) do not follow from the cells' yearly yields, "
                                                  f"e.g. {y}: written {x}, worked out {want}")


def check_live(root, runs):
    now = datetime.now(timezone.utc)
    for r in runs:
        rid = str(r.get("run_id", ""))
        if not RUN_ID.match(rid):
            continue                                     # reported by check_feed; never build a path from it
        lv = load(root / "runs" / rid / "live.json", 1, label=f"runs/{rid}/live.json")
        if lv is BAD:
            continue
        w = f"runs/{rid}/live.json"
        if lv.get("run_id") != rid:
            err(w, "run_id differs from the folder name")
        if not isinstance(lv.get("status"), str) or lv.get("status") not in STATUSES:
            err(w, f"status must be one of {sorted(STATUSES)}")
        if not isinstance(lv.get("process_alive"), bool):
            err(w, "process_alive must be true or false")
        t = utc_time(w + ".exported_at", lv.get("exported_at"))
        utc_time(w + ".last_activity", lv.get("last_activity"))
        if t and lv.get("status") not in ("finished", "failed"):
            age = (now - t).total_seconds()
            if age > 180:
                warn(w, f"written {int(age)} s ago: the card shows 'status unknown' until it is written again (every 60 s)")
            if age < -60:
                err(w, "exported_at is in the future: sync the server clock (NTP)")
        if lv.get("status") == "running" and lv.get("process_alive") is False:
            warn(w, "status running but process_alive false: the card will not say running")
        text2(w + ".step", lv.get("step"), 40, need=False)
        text2(w + ".note", lv.get("note"), 120, need=False)
        pr = lv.get("progress")
        if pr is not None:
            if not isinstance(pr, dict) or not isnum(pr.get("done")):
                err(w + ".progress", '{"done": n, "total": n, "what": {"en", "zh"}}')
            else:
                text2(w + ".progress.what", pr.get("what"), 30)


def check(root, allow_example=False):
    m = load(root / "manifest.json", 1)
    if m is BAD:
        err("manifest.json", "cannot check the other files without it")
        return
    runs = check_feed(m, allow_example)
    check_live(root, runs)
    P = check_page(as_dict("manifest.page", m.get("page")))
    if P is None:
        err("manifest.page", "grid_deg, years or cell_years are broken; the other files were not checked")
        return
    ver = str(m.get("data_version", ""))
    vdir = root / "v" / ver
    if not VERSION.match(ver) or not vdir.is_dir():
        err("manifest.data_version", f"the export folder v/{ver}/ does not exist; the other files were not checked")
        return
    for flat in ("cells.json", "units.json", "cell_years"):
        if (root / flat).exists():
            warn(flat, "from the older layout (not under v/); the page no longer reads it, you may delete it")
    units = check_units(load(vdir / "units.json", 30, label=f"v/{ver}/units.json"), P)
    c = load(vdir / "cells.json", 30, label=f"v/{ver}/cells.json")
    if not units:
        if isinstance(c, dict) and c.get("id"):
            err("units.json", "no well-formed units, so the cells could not be checked")
        return
    rows = check_cells(c, P, units)
    if not rows:
        return
    years_of = check_tiles(vdir, P, rows, units)
    check_numbers(c, P, units, rows, years_of)
    used = {r["unit"] for r in rows}
    for uid, u in units.items():
        if uid not in used and u.get("state") != "left_out":
            warn(f"units[{uid}]", "has no cells")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(args[0] if args else "app/public/data")
    check(root, "--allow-example" in sys.argv)
    for x in WARN:
        print("WARNING ", x)
    for x in ERR:
        print("ERROR   ", x)
    print(f"\n{root}: {len(ERR)} errors, {len(WARN)} warnings -> {'NOT ready to publish' if ERR else 'ready to publish'}")
    sys.exit(1 if ERR else 0)
