#!/usr/bin/env python3
"""Write MADE-UP example data so the page can be tried before your real results exist.

    python3 tools/make_example_data.py                 # writes example_tables/ and app/public/data/
    python3 tools/make_example_data.py --out /tmp/ex_data --tables /tmp/ex_tables      # somewhere else

It writes the same tables your run will write (texts.json, units.csv, cells.csv, reported.csv, model_years.csv,
final_settings.csv) and turns them into the page's data with tools/csv_to_data.py, exactly as you will. Open the
tables to see the shapes; docs/TUTORIAL.md explains every column.

Every unit here is invented ("Example North"), every number is generated, and the data carry "example": true, so the
page shows a yellow "Example data" banner and tools/check_data.py refuses it for publishing.
Only the Python standard library is used.
"""
import argparse
import csv
import json
import math
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "public" / "data"            # set from --out / --tables in main()
TABLES = ROOT / "example_tables"
G = 0.25                                    # cell size, degrees
YEARS = list(range(2010, 2025))
LAT0, LAT1, LON0, LON1 = 32.0, 38.0, 106.0, 118.0
rng = random.Random(11)

# id, English, Chinese, state, calibration years, validation years, true level t/ha, uncalibrated bias, note
UNITS = [
    ("EX-NW", "Example Northwest", "示例西北", "calibrated", (2010, 2018), (2019, 2024), 5.2, 1.35, None),
    ("EX-N", "Example North", "示例北部", "calibrated", (2010, 2018), (2019, 2024), 6.4, 0.80, None),
    ("EX-NE", "Example Northeast", "示例东北", "calibrated", (2014, 2019), (2020, 2024), 7.1, 1.20, None),
    ("EX-SW", "Example Southwest", "示例西南", "calibrating", (2010, 2018), (2019, 2024), 4.6, 1.25, None),
    ("EX-S", "Example South", "示例南部", "waiting", (2010, 2018), (2019, 2024), 5.8, 0.85, None),
    ("EX-SE", "Example Southeast", "示例东南", "left_out", (2010, 2018), (2019, 2024), 6.0, 1.0,
     ("No reported yields for this unit, so it cannot be calibrated.", "该单元没有统计产量，无法率定。")),
]
SETTINGS = [("P1", "Thermal time, emergence to end of juvenile", "出苗至幼苗期末积温", "°C·d"),
            ("P5", "Thermal time, silking to maturity", "吐丝至成熟积温", "°C·d"),
            ("G2", "Most kernels per plant", "单株最大籽粒数", "kernels"),
            ("SLPF", "Soil fertility factor", "土壤肥力因子", "")]

TEXTS = {
    "example": True,
    "project_id": "example-maize-calibration",
    "group": {"en": "Example group", "zh": "示例课题组"},
    "title": {"en": "Maize calibration (example)", "zh": "玉米率定（示例）"},
    "text": {"en": "KI agents set up, calibrate and check DSSAT maize on every grid cell, one unit at a time. "
                   "The map shows each cell's model yield and how each unit compares with reported yields.",
             "zh": "知识基础设施智能体在每个网格上设置、率定并检验 DSSAT 玉米模型，逐个单元进行。"
                   "地图显示每个网格的模拟产量，以及每个单元与统计产量的对比。"},
    "tags": {"en": ["DSSAT", "Maize", "Calibration", "0.25° grid"], "zh": ["DSSAT", "玉米", "率定", "0.25° 网格"]},
    "facts": "auto",
    "map_url": "https://example.org/maize/",
    "runs": [{"run_id": "example_run_2026_11", "name": {"en": "Maize calibration, example run", "zh": "玉米率定示例运行"},
              "started": "2026-11-01"}],
    "page": {
        "crop": {"en": "Maize", "zh": "玉米"},
        "model": {"en": "DSSAT 4.8 CERES-Maize", "zh": "DSSAT 4.8 CERES-Maize"},
        "region": {"en": "An invented region (example)", "zh": "虚构区域（示例）"},
        "method": {"en": "Each unit's settings are calibrated so that the model's yearly yield, weighted by crop area, "
                         "matches reported yields over its calibration years. Its validation years are kept out and "
                         "used only to check the result.",
                   "zh": "对每个单元的参数进行率定，使按作物面积加权的模拟年产量在率定年份与统计产量一致。"
                         "验证年份不参与率定，只用于检验结果。"},
        "reported_source": {"en": "Made-up numbers (example)", "zh": "虚构数据（示例）"},
        "unit_word": {"en": "unit", "zh": "单元"},
        "grid_deg": G,
        "years": [YEARS[0], YEARS[-1]],
        "water": [{"id": "rf", "name": {"en": "rainfed", "zh": "雨养"}},
                  {"id": "ir", "name": {"en": "irrigated", "zh": "灌溉"}}],
        "settings": [{"id": s, "name": {"en": en, "zh": zh}, **({"unit": u} if u else {})} for s, en, zh, u in SETTINGS],
        "cell_years": {"tile_deg": 5},
    },
}


def unit_at(lat, lon):
    row = 0 if lat >= (LAT0 + LAT1) / 2 else 1
    col = min(2, int((lon - LON0) / ((LON1 - LON0) / 3)))
    return UNITS[row * 3 + col]


def csv_write(name, head, rows):
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(head)
        w.writerows(rows)


def main():
    global OUT, TABLES
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--out", default=str(OUT), help="the data folder to write (default: app/public/data)")
    a.add_argument("--tables", default=str(TABLES), help="where to write the example tables (default: example_tables)")
    args = a.parse_args()
    OUT, TABLES = Path(args.out), Path(args.tables)
    weather = {u[0]: [rng.gauss(1, 0.12) for _ in YEARS] for u in UNITS}         # each unit's good and bad years
    for u in UNITS:
        weather[u[0]][YEARS.index(2021)] *= 0.75                                  # one dry year
    cells, model, true_unit = [], [], {u[0]: [[0.0, 0.0] for _ in YEARS] for u in UNITS}
    k = 0
    lat = LAT0 + G / 2
    while lat < LAT1:
        lon = LON0 + G / 2
        while lon < LON1:
            if rng.random() < 0.85:                                               # some squares have no maize
                u = unit_at(lat, lon)
                cid = f"C{k:05d}"; k += 1
                level = u[6] * (1 + 0.15 * math.sin(lat * 1.7) * math.cos(lon * 1.3)) * rng.uniform(0.85, 1.15)
                cold = lat > LAT1 - 0.6 and lon < LON0 + 1.5                      # a cold corner: the crop never finishes
                for water, share in (("rf", 1.0), ("ir", 0.35)):
                    if water == "ir" and rng.random() > 0.4:
                        continue
                    area = round(rng.uniform(200, 4000) * share, 1)
                    st = "left_out" if u[3] == "left_out" else "no_season" if cold else (
                        "calibrated" if u[3] == "calibrated" else "waiting")
                    cells.append([cid, water, f"{lat:.3f}", f"{lon:.3f}", u[0], area, st])
                    if st in ("left_out", "no_season") or u[3] == "waiting":
                        continue
                    boost = 1.25 if water == "ir" else 1.0
                    for i, y in enumerate(YEARS):
                        t = level * boost * weather[u[0]][i] * rng.gauss(1, 0.06)
                        failed = water == "rf" and rng.random() < 0.01             # a season with no grain
                        true = 0.0 if failed else t
                        true_unit[u[0]][i][0] += area * true
                        true_unit[u[0]][i][1] += area
                        base = 0.0 if failed else t * u[7] * rng.gauss(1, 0.05)
                        model.append([cid, water, "uncalibrated", y, f"{base:.3f}"])
                        if u[3] == "calibrated":
                            drift = 0.93 if y >= 2019 else 1.0                    # the model a bit low in later years
                            cal = 0.0 if failed else t * drift * rng.gauss(1, 0.05)
                            model.append([cid, water, "calibrated", y, f"{cal:.3f}"])
            lon += G
        lat += G

    reported = []
    for u in UNITS:
        if u[3] == "left_out":
            continue
        for i, y in enumerate(YEARS):
            a = true_unit[u[0]][i]
            v = a[0] / a[1] if a[1] else u[6] * weather[u[0]][i]
            usable = not (u[0] == "EX-N" and y in (2012, 2013)) and not (u[0] == "EX-NE" and y == 2022)
            reported.append([u[0], y, f"{v * rng.gauss(1.02, 0.04):.3f}", "true" if usable else "false"])

    units = [[u[0], u[1], u[2], "Example land", "示例国", u[3], u[4][0], u[4][1], u[5][0], u[5][1],
              u[8][0] if u[8] else "", u[8][1] if u[8] else "",
              120 if u[3] == "calibrating" else "", 300 if u[3] == "calibrating" else ""] for u in UNITS]
    final = [[u[0], rng.randint(180, 320), rng.randint(650, 900), rng.randint(600, 900), round(rng.uniform(0.7, 1.0), 2)]
             for u in UNITS if u[3] == "calibrated"]

    TABLES.mkdir(parents=True, exist_ok=True)
    (TABLES / "texts.json").write_text(json.dumps(TEXTS, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_write("units.csv", ["unit_id", "name_en", "name_zh", "parent_en", "parent_zh", "state", "cal_start", "cal_end",
                            "val_start", "val_end", "note_en", "note_zh", "progress_done", "progress_total"], units)
    csv_write("cells.csv", ["cell_id", "water", "lat", "lon", "unit_id", "area_ha", "state"], cells)
    csv_write("reported.csv", ["unit_id", "year", "yield_t_ha", "usable"], reported)
    csv_write("model_years.csv", ["cell_id", "water", "which", "year", "yield_t_ha"], model)
    csv_write("final_settings.csv", ["unit_id"] + [s[0] for s in SETTINGS], final)

    r = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "csv_to_data.py"), "--tables", str(TABLES),
                        "--out", str(OUT), "--allow-example"])
    if r.returncode:
        sys.exit("csv_to_data.py failed on the example tables (see above)")

    # the run's live status, as tools/status_writer.py would write it every 60 s
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    live = {"run_id": "example_run_2026_11", "status": "running", "process_alive": True, "exported_at": now,
            "last_activity": now, "step": {"en": "calibrating Example Southwest", "zh": "正在率定 示例西南"},
            "progress": {"done": 3, "total": 5, "what": {"en": "units calibrated", "zh": "个单元已率定"}}}
    p = OUT / "runs" / "example_run_2026_11" / "live.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(live, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, p)
    print(f"example tables in {TABLES}; example data in {OUT} (the run status says 'running' for 3 minutes, "
          f"then 'status unknown', as a real run would if its status writer stopped)")


if __name__ == "__main__":
    main()
