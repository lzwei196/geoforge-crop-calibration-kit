# GeoForge Global Runs: crop calibration kit

Show a gridded crop model calibration (DSSAT for now) as a live map page in the GeoForge style, with a card on
[geoforgehhu.com/global-runs.html](https://geoforgehhu.com/global-runs.html). 中文说明见 [README.zh.md](README.zh.md).

It is the same kind of page as the GeoForge global maize map: every grid cell on the map, each unit (country,
province or county) with its reported yields against the model, its own calibration and validation years, its
final settings and how well they do, and the honest status of your run.

## How it works

Everything runs on the computer where your run is. Nothing outside can reach that computer; a Cloudflare tunnel
carries your page out to a public address.

```
the computer where your run is
  DSSAT Summary.OUT ──> dssat_summary_to_csv.py ──> model_years.csv ─┐
  your tables (cells, units, reported yields, final settings) ────────┴─> csv_to_data.py ──> site/data/   map data
  your run (PID, log) ──> status_writer.py ──> site/data/runs/        "running now?" every 60 s
  serve.py      serves site/ (the page + data/) on 127.0.0.1 only
  cloudflared   carries it out through the tunnel
                                │
                                ▼
            https://<project>.geoforgehhu.com          your page, open to everyone
                                ▲
                                │ reads data/manifest.json and data/runs/*/live.json
            geoforgehhu.com/global-runs.html           your card, with an "Open the live map" button
```

You do not need a public IP, an open port, your own domain or a certificate. GeoForge makes the address and sends you
a tunnel key. If you prefer your own domain or web server, `docs/HOSTING.md` shows those ways too.

## What the page shows

- **The map:** every cell as a square, coloured by calibration state, crop area, model yield over calibration or
  validation years (calibrated or not), or its unit's yield ratio and R. One switch per water kind (e.g. rainfed /
  irrigated). Units not calibrated yet are drawn washed out.
- **A cell:** its crop area and model yield for every year, calibrated and uncalibrated, with the unit's calibration
  and validation years shaded.
- **A unit:** reported yields (grey dots = not usable) against the model, its final settings, and its yield ratio
  and R in calibration years and in validation years. A unit with no validation score says why.
- **All units:** a summary (how many scored, median yield ratio, how many within ±10 %, median R) and a table you can
  sort and filter; a click opens the unit and zooms the map to it.
- **The project and its runs:** texts, model, data source, and "Running now" only when it really is.

## Start here

**[The tutorial](docs/TUTORIAL.md)** (中文：[docs/TUTORIAL.zh.md](docs/TUTORIAL.zh.md)) walks through every step, in two parts:

1. **On your own computer (about a day):** try the example, write your texts, turn your run's results into the
   page's data, check them, build the page.
2. **On the computer where your run is (about an hour):** copy the page there, start three small services (the page
   server, the status writer and the tunnel), check from outside, and ask GeoForge for your card.

Try the example now (Python 3.8+ and Node 18+):

```
python3 tools/make_example_data.py    # made-up example data (clearly marked) into app/public/data/
(cd app && npm ci && npm run dev)    # open http://127.0.0.1:8870/
```

## What is inside

| Path | What it is |
| --- | --- |
| `app/` | the page (React + Leaflet + TypeScript, built with Vite) |
| `tools/dssat_summary_to_csv.py` | reads DSSAT `Summary.OUT` files into one table of yearly yields |
| `tools/csv_to_data.py` | turns your tables into the page's data, and computes the scores |
| `tools/check_data.py` | checks your data before you publish |
| `tools/status_writer.py` | writes your run's live status every 60 s |
| `tools/serve.py` | serves the page and data on this computer with the right headers |
| `tools/make_example_data.py` | writes made-up example data |
| `docs/TUTORIAL.md` | every step, from an empty computer to a live page and card |
| `docs/DATA_FORMAT.md` | every file and field the page reads, and how scores are computed |
| `docs/HOSTING.md` | the ways to get a public address, and the headers |
| `docs/GLOBAL_RUNS_FEED.md` | what your card on the Global Runs page reads, and the status rules |
| `docs/STYLE.md` | what to keep, what you may change, words, and what you may publish |
| `docs/CHECKLIST.md` | the last checks before going live |

## Rules in short

- Show only real results. Never write "running" unless the process is alive and working (the status writer does this).
- Data under `data/` is public as soon as the page is online. Leave out what you are not free to publish.
- Keep the header, the colours and the back button, so every Global Runs page feels like one family.
- The tunnel key never goes into code, chat or a repository.

## Known limits

- `serve.py` follows no links out of the site folder, but a folder on the path that is swapped for a link at the very
  moment of a request is not caught. Do not let other users write into the site folder.
- A failed winter-crop season with neither a harvest nor a maturity date is put in its planting year; if a good season
  was harvested in that same year, the DSSAT reader leaves that year empty (with a warning) instead of guessing.
- Data files edited by hand (not written by `csv_to_data.py`) can still show oddly on the page; `check_data.py`
  catches most such mistakes.
- A browser tab left asleep for more than half an hour may show "could not read" for one cell until the page
  reads the manifest again (within 2 minutes).
- The page needs JavaScript and a browser from the last few years.

Questions: open an issue in this repository.
