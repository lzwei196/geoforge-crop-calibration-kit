# Style and wording

Every Global Runs page should feel like one family: the same header, colours and plain wording. Readers come from the
Global Runs page and go back to it, often switching between projects.

## Keep as they are

- **The header, left to right:** back button (`← Global runs` / `← 全球运行`), title, search, language button, status badge.
  The back button always goes to the Global Runs page in the page's current language.
- **The colours:** only the tokens at the top of `app/src/styles.css`. Do not add new colours for decoration.
- **The map look:** a dark basemap, cells drawn as squares (waiting units washed out), the layer box at the top left, the stat strip under the map.
- **Honest status:** the status rule in `app/src/format.ts` (`stateOf`) is shared with the Global Runs page. Do not change it.
- **The example banner:** it shows whenever `"example": true`. Never publish with it.

## Free to change

- **Texts:** every text in `texts.json` (titles, crop, model, method, unit word, water and setting names). The nine map
  values are fixed by `csv_to_data.py` (`DATA_FORMAT.md`); to add one, change the tool and tell GeoForge.
- **Settings:** which calibrated settings you list, with plain names and units (`page.settings`).
- **Map start:** the first map view (`map.setView` in `MapView.tsx`). The page zooms to your cells by itself; only change it if you want a different start.
- **Extra panels:** new panels under the map (e.g. a table of the cells with the most crop area), in the same panel and card style.

## Words

- **Plain words:** say what the reader sees. "Kernels per plant", not "G2". If a term is needed
  (a cultivar coefficient, harvest index), explain it once in a note.
- **Both languages:** everything a reader sees has English and Chinese. Write the Chinese yourself; do not leave
  machine translation unchecked.
- **Fixed terms:** "KI agents" is "知识基础设施智能体" (not "AI 代理"); "Global Runs" is "全球运行".
- **Units:** in every label (`t/ha`, `ha`, `°C`). Numbers follow the reader's language (the page does this).
- **Calibration words:** "calibrate", never "fit". Data kept out to test a result is "validation" data.
- **No hype:** no "revolutionary", "AI-powered", exclamation marks or emoji.

## What you may publish

Everything in `data/` is public as soon as your page is online.

- **Unpublished results:** leave out results you are not yet free to show (e.g. while a paper is under review).
  Progress counts and step names are fine.
- **Other people's data:** do not put up data whose licence forbids sharing.
- **Personal data:** no people's names, e-mail addresses, user names, server paths or IP addresses in any file.
