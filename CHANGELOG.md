# Changelog

## 1.0.0 (2026-11-21)

First version: a live map page for a gridded crop model calibration (DSSAT), in the GeoForge Global Runs style.

- Page: every cell as a square (coloured by calibration state, crop area, yield over calibration or validation years,
  or the unit's yield ratio and R), a switch per water kind, cell panel with yearly lines, unit panel with reported vs
  model yields, final settings and scores, a sortable table of all units with a summary, the project and run status.
  English and Chinese.
- Tools: `dssat_summary_to_csv.py` (Summary.OUT to a table), `csv_to_data.py` (tables to the page's data, with the
  scores), `check_data.py`, `make_example_data.py`, `status_writer.py`, `serve.py` (now sends text files gzip-compressed).
- Docs: tutorial (EN + 中文), data format, hosting, Global Runs feed, style, checklist.
- Tested at full scale with the GeoForge global maize run's data (188,589 cell rows, 475 units).
