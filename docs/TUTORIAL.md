# Tutorial: from your run to a live page on GeoForge Global Runs

This walks you through every step, from an empty computer to your live page with a card on
[geoforgehhu.com/global-runs.html](https://geoforgehhu.com/global-runs.html). It uses a gridded DSSAT calibration as
the example: cells on a grid, units (provinces, counties) with reported yields, each unit calibrated over its own
calibration years and checked on its validation years. 中文版：[TUTORIAL.zh.md](TUTORIAL.zh.md).

## The idea in one picture

```
the computer where your run is
  your run ──(tables, Summary.OUT)──> csv_to_data.py ──> site/data/   map data     (step 8, then every hour)
  your run ──(PID, log)──> status_writer.py ──> site/data/runs/  "running now?"     (step 10, every 60 s)
  serve.py      serves site/ (the page + data/) on 127.0.0.1 only               (step 9)
  cloudflared   carries it out through the tunnel                               (step 11)
                                │
                                ▼
            https://<name>.geoforgehhu.com             your page, open to everyone
                                ▲
                                │ reads data/manifest.json and data/runs/*/live.json
            geoforgehhu.com/global-runs.html           your card (step 13)
```

- Your run is never touched: the tools only read its files.
- Nothing outside can reach the computer where your run is. The tunnel connects out to Cloudflare, and Cloudflare
  shows your page at the public address. No public IP, open port, domain or certificate is needed.
- GeoForge makes the address and sends you the tunnel key. Other ways (your own domain, your own web server) are in
  `HOSTING.md`.

Two parts:

| Part | Where | Steps | Time |
| --- | --- | --- | --- |
| A. Make the page | your own computer (a laptop is fine) | 1–7 | about a day |
| B. Put it online | the computer where your run is | 8–13 | about an hour |

## Before you start

| You need | Where | Check |
| --- | --- | --- |
| Python 3.8 or newer (only the standard library) | both computers | `python3 --version` |
| Node.js 18 or newer (only to build the page) | your own computer | `node --version` |
| git | both computers | `git --version` |
| Outgoing connections to Cloudflare on port 7844 | the computer where your run is | step 11 shows the check |
| sudo rights, systemd | the computer where your run is | to start the three small services |

# Part A. Make the page (your own computer)

## Step 1. Get the kit

The kit is a public repository on GitHub:

```
git clone https://github.com/lzwei196/geoforge-crop-calibration-kit.git
cd geoforge-crop-calibration-kit
```

## Step 2. Try the example

```
python3 tools/make_example_data.py
(cd app && npm ci && npm run dev)
```

Open http://127.0.0.1:8870/ and look around:

- a yellow "Example data" banner (all 6 units and their yields are made up);
- the cells as squares, coloured by calibrated yield; units not calibrated yet are washed out;
- the layer box (top left): colour by **Calibration state**, crop area, yield, or a unit's yield ratio and R, and
  switch between rainfed and irrigated;
- click a cell: its yearly model yield, calibrated and uncalibrated, with the calibration and validation years shaded;
- the unit on the right: reported yields (white dots, grey = not usable) against the model, the final settings and
  the scores; "Example Southeast" is left out and says why;
- the **All units** table: sort by a column, filter, click a row to zoom the map to that unit;
- the language button: every word switches, also the texts from `texts.json`;
- the status badge says "Running now" at first and "Status unknown (feed paused)" after 3 minutes: nothing keeps
  writing the example's status. That is the honest-status rule at work, not a fault.

Stop the dev server with Ctrl+C. The example tables the page was made from are in `example_tables/`; open them in an
editor or a spreadsheet. Step 4 makes the same six files from your run.

## Step 3. Write your texts

Copy the example's texts and change every line:

```
mkdir -p my_tables
cp example_tables/texts.json my_tables/
```

In `my_tables/texts.json`:

- **delete the line `"example": true`;**
- `project_id`: a short id agreed with GeoForge, e.g. `cn-wheat-calibration`;
- `map_url`: your page's address. You get it in step 11; until then leave the example's address (it must be an https
  address), and change it then;
- `group`, `title`, `text` (two sentences), `tags`: your project, in English and Chinese;
- `facts`: keep `"auto"` (the tool writes "120 / 312 units calibrated", the cell count and the years) or write up to
  4 of your own, each up to 40 characters;
- `runs`: your run, with a `run_id` (letters, digits, `_`, `-`) that stays the same for the whole run;
- `page.crop`, `page.model` (e.g. "DSSAT 4.8 CERES-Wheat"), `page.region`, `page.method` (how the calibration works,
  in two or three plain sentences), `page.reported_source` (where the reported yields come from), `page.unit_word`
  (e.g. "province" / "省");
- `page.grid_deg`: your cell size in degrees; `page.years`: the first and last year the model runs;
- `page.water`: your water kinds (e.g. `rf` rainfed, `ir` irrigated), or one kind `all`;
- `page.settings`: the settings your calibration chooses, with a plain name, unit and note each (e.g. `G2`, "most
  kernels per plant", "kernels"). Only those listed here are shown.

Plain words: say "calibrate", never "fit"; years kept out to test the result are "validation" years. More in `STYLE.md`.

## Step 4. Turn your run's results into the page's data

The page is made from six files in one folder (`my_tables/`). The first is your texts (step 3); the other five are
tables your run already has in some form. The exact columns are below and in the example files. Write empty cells
for "no value", never -99.

| File | One row per | Columns |
| --- | --- | --- |
| `units.csv` | unit | `unit_id, name_en, name_zh, parent_en, parent_zh, state, cal_start, cal_end, val_start, val_end, note_en, note_zh, progress_done, progress_total` |
| `cells.csv` | cell and water kind | `cell_id, water, lat, lon, unit_id, area_ha, state` |
| `reported.csv` | unit and year | `unit_id, year, yield_t_ha, usable` |
| `model_years.csv` | cell, water kind, line and year | `cell_id, water, which, year, yield_t_ha` |
| `final_settings.csv` | calibrated unit | `unit_id`, then one column per `page.settings` id |

What the columns mean:

- `units.csv` `state`: `waiting`, `calibrating`, `calibrated` or `left_out`. A calibrated unit must have a row in
  `final_settings.csv`. `cal_start`–`cal_end` and `val_start`–`val_end` are the unit's own years (leave `val_*` empty
  if it has no validation years). `note_*`: one plain line the reader should know, e.g. "Left out: fewer than 2
  reported years". `progress_*`: rounds done and planned while the unit is calibrating.
- `cells.csv` `lat`, `lon`: the cell centre. `area_ha`: the crop area of this water kind in the cell. `state`:
  `waiting`, `calibrated`, `left_out` (not run) or `no_season` (run, but no season in any year: the crop never
  finishes, e.g. too cold). Rows of 0 or empty for such a cell are ignored (the DSSAT reader writes 0 for its failed
  seasons); a positive yield for it stops the export, because then the cell did have a season.
- `reported.csv` `usable`: `false` for a reported year you do not trust (a break in the series, a known error). It
  is drawn grey and never scored.
- `model_years.csv` `which`: `uncalibrated` (starting settings) or `calibrated` (the unit's final settings). A season
  that was run and gave no grain is `0`; a year that was not run is empty.

**From DSSAT output.** `model_years.csv` can be read straight from your `Summary.OUT` files. List them in an index
file, one line per cell, water kind and line:

```
cell_id,water,which,path
N36E117a,rf,uncalibrated,/data/run/base/N36E117a_rf/Summary.OUT
N36E117a,rf,calibrated,/data/run/final/N36E117a_rf/Summary.OUT
```

```
python3 tools/dssat_summary_to_csv.py --index my_index.csv --crop WH --first-year 2010 --last-year 2024 --out my_tables/model_years.csv
```

- `--crop`: the DSSAT crop code in the `CR` column (`MZ` maize, `WH` wheat, `RI` rice, `SB` soybean, …); fallow and
  other crops in a sequence run are skipped.
- `--first-year`, `--last-year`: keep only seasons in these years (use `page.years`). DSSAT sequence runs often start
  with warm-up years, e.g. 1976, which the page does not show.
- `--year-from harvest` (default) gives each season the year it is harvested, like most yield statistics; when the
  harvest date is missing it uses the maturity date, then the planting date. `--year-from planting` uses the planting year.
- A row with an unreadable yield (blank, `****`, a negative other than -99) is skipped and counted, never turned into 0.
- Files that do not exist yet (units not calibrated yet) are counted as "not there yet"; a file that exists but cannot
  be read stops the tool with an error, so the export after it does not run on a broken table.
- A planted season with `HWAM` -99 (the crop failed) is written as `0`; `--failed missing` leaves it empty instead.
- If one file has two seasons in the same year, that year is left empty and the tool warns you: it never guesses.

Then make the data:

```
python3 tools/csv_to_data.py --tables my_tables --out my_data --dry-run     # checks only, writes nothing
python3 tools/csv_to_data.py --tables my_tables --out my_data
```

It also works out what the page shows, the same way every time (details in `DATA_FORMAT.md`):

- each unit's yearly model yield: the crop-area-weighted mean of its cells, only when the cells with a value hold at
  least 90 % of the crop area of its counted cells (cells left out or with no season are not counted, so they never
  pull this below 90 %);
- the scores of each calibrated unit, for calibration years and for validation years: **yield ratio** (model mean ÷
  reported mean over the usable years; 1 = right level) and **R** (do model and reports rise and fall together);
- the map values of each cell.

So you do not compute scores yourself, and the page and the numbers always agree. If your own calibration uses
another score, say so in `page.method`.

## Step 5. Check your data

```
python3 tools/check_data.py my_data
```

It checks every file and works the numbers out again from the files. Fix every error it lists; it ends with "ready to
publish" when there are none. (`live.json: missing` is expected until step 10.)

## Step 6. See your own data

```
rm -rf app/public/data && cp -r my_data app/public/data
(cd app && npm run dev)
```

Open http://127.0.0.1:8870/ again. Check:

- the cells are where your crop is (the map zooms to them by itself);
- click a few cells in different units: crop area, yearly lines and the shaded years look right;
- open a few units from the table: reported yields, final settings and scores match what your run says;
- units that are waiting or left out say so, and the notes read well;
- switch to 中文 and read every text once more;
- make the window narrow (about 390 px, like a phone): everything is still usable.

What you may change in the page code and what must stay is in `STYLE.md` (keep the header, colours and the status rule).

## Step 7. Build the page

```
(cd app && npm run build)
```

This writes `app/dist/` (`index.html` and `assets/`). You build again only when the page code changes, not when the
data change.

# Part B. Put it online (the computer where your run is)

In the examples below, the user that runs everything is `crop`, the run's folder is `/data/run`, its tables are in
`/data/out/tables`, and the run is `cn_wheat_2026_11`. Change these to yours. If your run is on a cluster or the page should be
served from another computer, read "When the run is on another computer" in `HOSTING.md` first.

## Step 8. Set up the site folder

Make the two folders, the kit and the site (the page plus its data), and put the kit there:

```
sudo mkdir -p /opt/geoforge-crop-kit /opt/geoforge-site
sudo chown crop /opt/geoforge-crop-kit /opt/geoforge-site
git clone https://github.com/lzwei196/geoforge-crop-calibration-kit.git /opt/geoforge-crop-kit
```

If this computer cannot reach GitHub, copy the kit from your own computer instead:
`rsync -a --exclude node_modules ./ crop@run-computer:/opt/geoforge-crop-kit/`.

Copy from your own computer: the built page into the site folder, and your texts next to the run's tables.

```
rsync -a app/dist/ crop@run-computer:/opt/geoforge-site/
scp my_tables/texts.json crop@run-computer:/data/out/tables/
```

Your run writes the five tables (step 4) on this computer, here in `/data/out/tables/` (run
`dssat_summary_to_csv.py` there first if you read `Summary.OUT` files). Write the data once and check it:

```
cd /opt/geoforge-crop-kit
python3 tools/csv_to_data.py --tables /data/out/tables --out /opt/geoforge-site/data
python3 tools/check_data.py /opt/geoforge-site/data
```

Only the `live.json: missing` error is expected now; step 10 fixes it.

## Step 9. Start the page server

`tools/serve.py` serves the site folder with the right headers, on this computer only (`127.0.0.1`, port 8871).
Try it:

```
python3 tools/serve.py --site /opt/geoforge-site
curl -sI http://127.0.0.1:8871/data/manifest.json        # in a second terminal: must say 200
```

Stop it with Ctrl+C and make it a service, so it runs after every reboot. Save as
`/etc/systemd/system/geoforge-site.service`:

```ini
[Unit]
Description=GeoForge page server
After=network.target

[Service]
User=crop
ExecStart=/usr/bin/python3 /opt/geoforge-crop-kit/tools/serve.py --site /opt/geoforge-site
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload && sudo systemctl enable --now geoforge-site
```

## Step 10. Start the status writer

The status writer tells readers and the Global Runs card whether your run is really working. It must run on the same
computer as your run's process, because it checks the process by its id. It needs two things from your run:

- **a PID file**: a file holding the process id of your run. If your run does not write one, start it like this:
  `nohup python3 run_calibration.py > run.log 2>&1 & echo $! > run.pid`
- **an activity file**: a log file your run writes to while it works (here `run.log`). Use a file, not a big folder.

Try it (it keeps writing every 60 s until you press Ctrl+C):

```
python3 tools/status_writer.py --data /opt/geoforge-site/data --run-id cn_wheat_2026_11 \
    --pid-file /data/run/run.pid --activity /data/run/run.log \
    --step-en "calibration" --step-zh "率定"
```

In a second terminal, look at `/opt/geoforge-site/data/runs/cn_wheat_2026_11/live.json`: `status` is `running` only while
your run's process exists.

**Progress:** to show "120 / 312 units calibrated", change the `progress()` function in `tools/status_writer.py` to count what
your run has finished, for example result files:

```python
def progress():
    done = len(list(Path("/data/run/final_settings").glob("*.json")))   # one file per calibrated unit
    return {"done": done, "total": 312, "what": {"en": "units calibrated", "zh": "个单元已率定"}}
```

Make it a service. Save as `/etc/systemd/system/geoforge-status.service`:

```ini
[Unit]
Description=GeoForge status writer
After=network.target

[Service]
User=crop
ExecStart=/usr/bin/python3 /opt/geoforge-crop-kit/tools/status_writer.py --data /opt/geoforge-site/data --run-id cn_wheat_2026_11 --pid-file /data/run/run.pid --activity /data/run/run.log --step-en "calibration" --step-zh "率定"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl daemon-reload && sudo systemctl enable --now geoforge-status
```

**When the run ends or pauses,** say so yourself; a dead process alone only means "stopped":

- **Finished:** switch the service off for good (otherwise it starts again after a reboot and writes "stopped" over
  "finished"), then write `finished` once:

  ```
  sudo systemctl disable --now geoforge-status
  python3 tools/status_writer.py --data /opt/geoforge-site/data --run-id cn_wheat_2026_11 --pid-file /data/run/run.pid --activity /data/run/run.log --status finished
  ```

- **Paused:** add `--status paused --note-en "Waiting for new yield statistics" --note-zh "等待新的统计产量"` to the service's
  `ExecStart` line, then run `sudo systemctl daemon-reload && sudo systemctl restart geoforge-status`. Take it out
  again (and reload, restart) when the run goes on.

## Step 11. Get your public address

1. Write to GeoForge (an issue in this repository, or as agreed) with your `project_id` and ask for an address. We
   make one like `https://cn-wheat.geoforgehhu.com` and send you the tunnel key privately.
2. Check that this computer can reach Cloudflare's tunnel port (outgoing TCP and UDP 7844; nothing comes in):

   ```
   nc -vz region1.v2.argotunnel.com 7844        # must say "succeeded" or "open"
   ```

   (If `nc` is missing: `sudo apt install netcat-openbsd`.)

   If it fails, ask your network administrator to allow outgoing connections to Cloudflare on port 7844.
3. Install `cloudflared` 2025.4 or newer. GitHub downloads can be slow from mainland China, so download it on your
   own computer and copy it over (ARM computers: `cloudflared-linux-arm64.deb`; other systems: the
   [downloads page](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/)):

   ```
   curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   scp cloudflared.deb crop@run-computer:
   ```

   Then on the run's computer: `sudo dpkg -i cloudflared.deb && cloudflared --version`.
4. Save the key in a file only root can read. Never put it on a command line, where other users of the computer could
   see it:

   ```
   sudo mkdir -p /etc/cloudflared
   sudo sh -c 'umask 077; read -r k; printf %s "$k" > /etc/cloudflared/geoforge.token'    # paste the key, press Enter
   ```

5. Make the tunnel a service. Save as `/etc/systemd/system/geoforge-tunnel.service`:

   ```ini
   [Unit]
   Description=GeoForge tunnel
   After=network-online.target
   Wants=network-online.target

   [Service]
   ExecStart=/usr/bin/cloudflared --no-autoupdate tunnel run --token-file /etc/cloudflared/geoforge.token
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

   ```
   sudo systemctl daemon-reload && sudo systemctl enable --now geoforge-tunnel
   systemctl status geoforge-tunnel        # "active (running)"; the log shows "Registered tunnel connection"
   ```

6. Open your address in a browser: your page appears.

Keep the key secret: not in code, chat or a repository. If it leaks, tell us; we make a new one and the old one stops
working. Your own domain or web server instead: `HOSTING.md`, ways 2 and 3. If you did not know the address in
step 3 (your texts), put it in `map_url` of `texts.json` now and run the export (step 8) again.

## Step 12. Check from outside

From any other computer:

```
curl -sI -H "Origin: https://geoforgehhu.com" https://cn-wheat.geoforgehhu.com/data/manifest.json
```

It must show `200`, `Access-Control-Allow-Origin: https://geoforgehhu.com` and `Cache-Control: no-store`. On the run's
computer, `python3 tools/check_data.py /opt/geoforge-site/data` must now say "ready to publish". Open your page on a
phone. Then go through `CHECKLIST.md` and tick every box.

## Step 13. Join Global Runs

Send GeoForge:

1. your page address and `project_id`;
2. one picture for the card: JPG, 1200 × 800 px, under 300 KB, no text on it (a map screenshot works well);
3. the card text in English and Chinese: a title (up to 80 characters), two sentences, and up to 6 tags;
4. a contact for status questions (we will not publish it).

What happens then:

1. We read your files for a day to see that the status stays fresh and honest.
2. We show you the card in both languages and agree the wording.
3. We add the card and tell you it is live. It shows the first 3 `facts` and your runs' status, read from your
   address; the picture, title, text, tags and button address stay as agreed (send us changes).

When every run is `finished`, your card moves to the "Finished" section by itself. To take it down, set every run to
`finished` or `stopped` and tell us; it is removed the same day.

# After going live

## While the run goes on

New results: run the export again, for example every hour from cron (as the user `crop`, `crontab -e`):

```
0 * * * *  cd /opt/geoforge-crop-kit && flock -n /tmp/geoforge-export.lock sh -c 'python3 tools/dssat_summary_to_csv.py --index /data/out/my_index.csv --crop WH --first-year 2010 --last-year 2024 --out /data/out/tables/model_years.csv && python3 tools/csv_to_data.py --tables /data/out/tables --out /opt/geoforge-site/data' >> /tmp/geoforge-export.log 2>&1
```

- First the `Summary.OUT` files are read again (so new seasons come in), and only if that worked is the data exported.
  Leave out the first part if your run writes `model_years.csv` itself.
- Use the same `--crop`, `--year-from` and `--failed` options as in step 4, so the hourly run reads the files the same way.
- `flock` skips a round while the last export is still going.
- If nothing changed, the export writes nothing, so open pages do not download everything again.
- Let your pipeline finish writing each CSV before the export reads it (write to a temporary name, then rename).
- Open pages pick new data up within 2 minutes (they look for a new `data_version`). The status writer keeps going on
  its own.

A new run (for example the global one): add it at the top of `runs` in `texts.json`, export again, and make a
second status writer service with the new `--run-id`.

## Going from one country to the world

No code change is needed. Add the units, cells and years to your tables. Check:

- one `cell_years` file stays under about 20 MB; if a 5° square gets too big, set `page.cell_years.tile_deg` to 2 or 1;
- `cells.json` is read by every visitor: about 200,000 cell rows (about 30 MB, 5 MB compressed) is fine; tell us
  before you go beyond that;
- units with their own calibration and validation years keep them (`cal_*`, `val_*` in `units.csv`).

## Getting fixes from GeoForge

We push fixes to this repository. On your own computer:

```
git pull
cat CHANGELOG.md                     # what changed
(cd app && npm ci && npm run build)
rsync -a app/dist/ crop@run-computer:/opt/geoforge-site/     # never add --delete: it would delete data/
```

On the run's computer, update the tools with `cd /opt/geoforge-crop-kit && git pull`. If you changed
`progress()` in step 10, git keeps your change aside and puts it back: `git stash && git pull && git stash pop`. Then
`sudo systemctl restart geoforge-site`, and `sudo systemctl restart geoforge-status` only while the run is still going
(after `finished` it would write "stopped" again). Your data and tables are not touched by a pull.

## When something is wrong

| You see | Likely reason | Fix |
| --- | --- | --- |
| Cloudflare "Error 1033" at your address | the tunnel is not connected | `systemctl status geoforge-tunnel`; the port 7844 check in step 11 |
| Cloudflare "502 Bad Gateway" | the tunnel works, but the page server does not answer | `systemctl status geoforge-site`; `curl -sI http://127.0.0.1:8871/` |
| "Status unknown (feed paused)" | `live.json` older than 3 minutes | `systemctl status geoforge-status`; check the clock is synced (NTP) |
| "Stopped" while the run works | the PID in the PID file is not the run's process | write the PID of the real run process (not a wrapper that exits) |
| "Running" after the run ended | an old PID file whose number is now used by another process | remove the PID file when the run ends; write `finished` (step 10) |
| The page says the data cannot be read | no `data/` yet, or a broken file | run the export (step 8) and `check_data.py` |
| The card on Global Runs shows no status | the browser cannot read your files from geoforgehhu.com | step 12's `curl` must show the `Access-Control-Allow-Origin` line |
| New data do not appear | the export failed or found nothing new | check `/tmp/geoforge-export.log` |
| A cell shows 0 where you expected nothing | a year that was not run written as 0 | write it empty in `model_years.csv`; only a season that gave no grain is 0 |
| A unit has no validation score | fewer than 2 usable reported years in its validation years | that is right; say why in its `note_en` / `note_zh` |
| A calibrated unit shows no model line | the cells with a value hold less than 90 % of its counted crop area in those years | check the missing years in `model_years.csv`; a cell where the crop never finishes should be `no_season` in `cells.csv` |

Other questions: open an issue in this repository.
