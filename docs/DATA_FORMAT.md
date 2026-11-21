# Data format (version 1)

The page reads plain JSON files from a `data/` folder next to its `index.html`. You do not write these files by hand:
`tools/csv_to_data.py` writes them from a few CSV tables that your run already has (see `TUTORIAL.md`, part 1).
`tools/make_example_data.py` writes a full made-up set you can open and copy from, and `tools/check_data.py` checks
your real files before you publish.

```
data/
  manifest.json                          the project: texts, crop, model, settings, runs, which version to read
                                         (read by your page AND the Global Runs card)
  v/<data_version>/cells.json            every grid cell, one list per column
  v/<data_version>/units.json            every unit (province, state, county…): years, reported yields, final settings, scores
  v/<data_version>/cell_years/<lat>_<lon>.json   each cell's yearly model yield, one file per 5° square
  runs/<run_id>/live.json                how each run is doing right now (read by your page AND the Global Runs card)
```

Every export goes into a new folder `v/<data_version>/`, and `manifest.json` says which one to read. A reader therefore
never mixes files of two exports: a page that still holds the old manifest keeps reading the old folder, which stays
for a while (see the end of this file).

## Words used here

- **cell**: one grid square (for example 0.1° × 0.1°) where the crop grows.
- **water**: how the crop is grown in a cell, for example rainfed or irrigated. One cell can have more than one;
  each is a separate row in `cells.json` and a separate DSSAT run. If you only have one, use one (e.g. `all`).
- **unit**: the area that reports yields (a country, province or county). Every cell belongs to one unit. A unit is
  calibrated as a whole: one set of final settings for all its cells.
- **calibration years / validation years**: each unit has its own. Calibration years are used to choose the
  settings; validation years are kept out of that and used only to check the result.
- **settings**: the values the calibration chooses, for example cultivar coefficients (`P1`, `P5`, `G2`, `G3`) or a
  soil fertility factor (`SLPF`).
- **calibrated / uncalibrated**: the model yield with the unit's final settings / with the starting settings.

## Rules for every file

- UTF-8 JSON. Write each file to a temporary name first, then rename it (`os.replace`), so no reader ever sees half a file.
- Every text a reader sees is `{"en": "...", "zh": "..."}`, both filled in.
- Times are UTC with the zone: `2026-10-22T03:07:15+00:00`. Years are whole numbers.
- Yields are in **t/ha** (DSSAT `HWAM` is kg/ha: divide by 1000).
- `null` means "no value". Never write -99 or -9999 for a missing value: the page would draw it as a real number.
  A season that was run and gave no grain is a real `0`, not `null`.
- Never write `NaN` or `Infinity`: they are not JSON, and a browser then cannot read the WHOLE file.

## manifest.json

The top part is the Global Runs feed (see `GLOBAL_RUNS_FEED.md`); `page` holds what only your page needs.

| Field | Type | Meaning |
| --- | --- | --- |
| `feed_version` | `1` | format version |
| `project_id` | a–z, 0–9, `-` | your project's short id, agreed with GeoForge |
| `example` | `true` / absent | only in example data; the page shows a yellow banner and the checker refuses it |
| `updated_at` | UTC time | when the data last changed; always later than the one before |
| `data_version` | text (a–z, A–Z, 0–9, `_`, `-`) | the folder under `v/` that holds this export; the page re-reads the other files only when it changes |
| `group` | text, ≤ 80 | your group's name |
| `title` | text, ≤ 80 | your page's title |
| `text` | text, ≤ 400 | two sentences: what the agents do |
| `tags` | `{"en": [...], "zh": [...]}`, 1–6 | short labels |
| `facts` | up to 4 texts, each ≤ 40 | short facts, e.g. "312 provinces"; the Global Runs card shows the first 3 |
| `map_url` | https address with a host | where your page lives (required) |
| `runs` | list | `{"run_id", "name": text, "started": "YYYY-MM-DD"}`, newest first |
| `page` | object | below |

`page`:

| Field | Type | Meaning |
| --- | --- | --- |
| `crop` | text | e.g. `{"en": "Wheat", "zh": "小麦"}` |
| `model` | text | e.g. `{"en": "DSSAT 4.8 CERES-Wheat", "zh": "DSSAT 4.8 CERES-Wheat"}` |
| `region` | text | the area covered |
| `method` | text, ≤ 400 | how the calibration works, in two or three plain sentences |
| `reported_source` | text | where the reported yields come from, e.g. "FAOSTAT and national statistics" |
| `unit_word` | text | what one unit is called, e.g. `{"en": "province", "zh": "省"}` |
| `grid_deg` | number | cell size in degrees, e.g. `0.1`; cell centres sit at odd multiples of half of it |
| `years` | `[first, last]` | the years the model runs, e.g. `[2010, 2024]` |
| `water` | list | `{"id": "rf", "name": text}` for each water kind, in menu order |
| `settings` | list | `{"id": "G2", "name": text, "unit": "kernels/plant", "note": text}`; `name`, `unit`, `note` may be left out |
| `values` | list | what can colour the map: `{"id", "name": text, "unit", "kind": "num", "scale"?: "sequential" or "diverging", "center"?: number, "note"?: text}` |
| `default_value` | id | the value the map opens with |
| `cell_years` | object | `{"tile_deg": 5}` (a whole number that divides 180) |

`values` are filled in `cells.json`. `csv_to_data.py` writes these nine, with their names, units and notes:
`area_ha`; `cal_yield_calibration`, `cal_yield_validation`, `base_yield_calibration`, `base_yield_validation` (the
cell's calibrated / uncalibrated mean yield over its unit's calibration / validation years, only when every year of
the period has a value); `unit_ratio_calibration`, `unit_ratio_validation`, `unit_r_calibration`,
`unit_r_validation` (the unit's scores, shown on each of its cells, also on cells that are left out or have no
season). These nine are fixed: every export writes them again, so do not add or edit values by hand; the checker
requires all nine. The page always adds one
more choice by itself, **Calibration state**, coloured from `cells.json` `state`. A `diverging` value is coloured
around `center` (default 0; use 1 for a yield ratio).

## cells.json

One row per cell and water kind. Every list has the same length and the same order. One grid square has one cell id, and
one row per water kind at most.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | text | the cell id, the same for every water kind of that cell, never changes between updates |
| `water` | text | a `page.water` id |
| `lat`, `lon` | number | the cell centre |
| `unit` | text | the `units.json` id of the cell's unit |
| `area_ha` | number or `null` | crop area of this water kind in the cell (hectares) |
| `state` | 0, 1, 2 or 3 | 0 = waiting, 1 = calibrated (its unit has final settings), 2 = left out (not run), 3 = run but no season in any year (e.g. too cold: the crop never finishes; such a cell has no yearly yield at all) |
| `values` | `{value_id: [number or null, …]}` | one list per `page.values` entry |

```json
{"id": ["N36E117a", "N36E117a", "N36E117b"], "water": ["rf", "ir", "rf"], "lat": [36.05, 36.05, 36.15],
 "lon": [117.05, 117.05, 117.05], "unit": ["CN-SD", "CN-SD", "CN-SD"], "area_ha": [410.5, 120.0, 388.2],
 "state": [1, 1, 1], "values": {"cal_yield_calibration": [6.41, 7.82, 6.12], "...": []}}
```

## units.json

`{"units": [ … ]}`, one object per unit:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | text | unit id, used in `cells.json` |
| `name` | text | e.g. `{"en": "Shandong", "zh": "山东"}` |
| `parent` | text or absent | e.g. the country |
| `state` | text | `waiting`, `calibrating`, `calibrated` or `left_out` |
| `note` | text or absent | one plain line the reader should know, e.g. why it is left out |
| `periods` | object | `{"calibration": [2010, 2018], "validation": [2019, 2024]}`; `validation` may be `null` |
| `reported` | object | `{"years": [...], "yield": [t/ha or null], "usable": [true/false]}`; a year marked not usable is shown grey and never scored |
| `model` | object | `{"years": [...], "calibrated": [...], "uncalibrated": [...]}`: `years` is every year of `page.years`; the unit's yield from its cells, weighted by crop area (rule below); `null` where there is no value |
| `final` | object or `null` | `null` until the unit is calibrated; then `{"settings": {"G2": 820, …}, "scores": {"calibration": S, "validation": S or null}}` |
| `progress` | object or absent | while calibrating: `{"done": 120, "total": 300, "what": text}`; `csv_to_data.py` counts rounds ("rounds" / "轮") |

A score object `S` is `{"n": years compared, "ratio": model mean / reported mean, "r": correlation of the yearly values}`.
`ratio` is `null` when there are fewer than 2 such years or the reported mean is 0; `r` is `null` when there are
fewer than 3 years or the model or the reported yields are the same in every year (then a correlation means nothing). `csv_to_data.py` computes them
from `reported` and `model` with exactly this rule, so the page and the numbers always agree:

- use the years in the period where the reported yield is usable and the calibrated model value is not `null`;
- `ratio` = mean of model ÷ mean of reported over those years (1 = the right level, 0.9 = model 10 % low);
- `r` = Pearson correlation of the same pairs (does the model follow the good and bad years?).

**Unit model yield (rule):** for each year, the crop-area-weighted mean over the unit's counted cells (all water
kinds) that have a value in that year, but only when those cells hold at least 90 % of the crop area of all its
counted cells; otherwise `null`. Counted cells are those that are waiting or calibrated (state 0 or 1) and have crop
area. Cells left out (state 2) and cells with no season (state 3) are not counted (for a no-season cell, rows of 0
or empty in `model_years.csv` are ignored; a positive yield stops the export), and a cell with no crop area
(`area_ha` null or 0) has no weight. "At least 90 %" allows for rounding: covered ≥ 0.9 × total − 1e-9 × total.

## cell_years/&lt;lat&gt;_&lt;lon&gt;.json

Each cell's model yield for every year, split into squares of `tile_deg` degrees so the page reads only what a reader
clicks. The file name is the square's south-west corner: `floor(lat / tile_deg) * tile_deg`, same for `lon`. A cell at
36.05° N, 117.05° E with `tile_deg` 5 is in `cell_years/35_115.json`.

```json
{"years": [2010, 2011, 2012], "cells": {"N36E117a|rf": {"calibrated": [6.1, 0, 6.8], "uncalibrated": [5.2, 0, 5.9]}}}
```

Keys are `<cell id>|<water id>`. `calibrated` is absent (or all `null`) while the unit is not calibrated yet. A file is
written for every square that holds a cell, even when none of its cells has yearly values yet (then `"cells": {}`),
so a missing file always means an error. Values keep up to 6 decimals.

## runs/&lt;run_id&gt;/live.json

Exactly as in `GLOBAL_RUNS_FEED.md`. `tools/status_writer.py` writes it every 60 seconds.

## When the data changes

`csv_to_data.py` does all of this for you:

1. If nothing changed since the last export, it writes nothing (so open pages do not download everything again).
2. Otherwise it writes the new folder `v/<data_version>/` completely, then `manifest.json` with the new
   `data_version` and `updated_at` last.
3. It removes old folders under `v/`, but keeps the one before the new one and every folder that stopped being the
   current one less than 30 minutes ago, so a page that read the old manifest a moment ago can still finish reading.
4. Only one export runs at a time (a lock file `.export.lock` in the data folder).

The page checks `manifest.json` every 2 minutes and reads the rest again only when `data_version` changed.
