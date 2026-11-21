# GeoForge 全球运行：作物率定工具包

把网格化的作物模型率定（目前为 DSSAT）做成 GeoForge 风格的实时地图页面，并在
[geoforgehhu.com/cn/global-runs.html](https://geoforgehhu.com/cn/global-runs.html) 上显示一张卡片。English: [README.md](README.md)。

它和 GeoForge 全球玉米地图是同一类页面：地图上显示每个网格；每个单元（国家、省或县）显示统计产量与模拟产量的对比、
它自己的率定年份和验证年份、最终参数及其表现；同时如实显示你的运行状态。

## 工作方式

所有程序都在运行所在的电脑上。外部无法访问这台电脑；Cloudflare 隧道把你的页面送到一个公开地址。

```
运行所在的电脑
  DSSAT Summary.OUT ──> dssat_summary_to_csv.py ──> model_years.csv ─┐
  你的表格（网格、单元、统计产量、最终参数） ─────────────────────────┴─> csv_to_data.py ──> site/data/   地图数据
  你的运行（PID、日志） ──> status_writer.py ──> site/data/runs/       “是否正在运行”，每 60 秒
  serve.py      只在 127.0.0.1 上提供 site/（页面 + data/）
  cloudflared   通过隧道把页面送出去
                                │
                                ▼
            https://<项目名>.geoforgehhu.com           你的页面，所有人可访问
                                ▲
                                │ 读取 data/manifest.json 和 data/runs/*/live.json
            geoforgehhu.com/cn/global-runs.html        你的卡片，带“打开实时地图”按钮
```

你不需要公网 IP、开放端口、自己的域名或证书。GeoForge 为你建好地址并发给你隧道密钥。如果你想用自己的域名或网站服务器，
`docs/HOSTING.md` 也介绍了这些方式。

## 页面显示什么

- **地图：**每个网格是一个方块，可按率定状态、种植面积、率定年份或验证年份的模拟产量（率定后或率定前），或所在单元的
  产量比和 R 着色。每种水分条件一个切换按钮（例如雨养 / 灌溉）。尚未率定的单元颜色变淡。
- **一个网格：**种植面积和每年的模拟产量（率定后和率定前），单元的率定年份和验证年份用浅色底标出。
- **一个单元：**统计产量（灰点 = 不可用）与模拟产量的对比、最终参数，以及率定年份和验证年份的产量比和 R。
  没有验证评分的单元会说明原因。
- **全部单元：**汇总（多少单元有评分、产量比中位数、多少在 ±10 % 以内、R 中位数）和一张可排序、可筛选的表格；
  点击一行会打开该单元并把地图缩放到它。
- **项目和运行：**文字、模型、数据来源；只有真的在运行时才显示“正在运行”。

## 从这里开始

**[教程](docs/TUTORIAL.zh.md)**（English: [docs/TUTORIAL.md](docs/TUTORIAL.md)）分两部分讲解每一步：

1. **在你自己的电脑上（约一天）：**试运行示例，写好文字，把运行结果转成页面数据，检查，构建页面。
2. **在运行所在的电脑上（约一小时）：**把页面复制过去，启动三个小服务（页面服务、状态写出、隧道），从外部检查，
   然后向 GeoForge 申请卡片。

现在就可以试运行示例（需要 Python 3.8+ 和 Node 18+）：

```
python3 tools/make_example_data.py    # made-up example data (clearly marked) into app/public/data/
(cd app && npm ci && npm run dev)    # open http://127.0.0.1:8870/
```

第一行生成虚构的示例数据（已明确标注）到 `app/public/data/`；第二行启动页面，然后打开 http://127.0.0.1:8870/。

## 内容

| 路径 | 说明 |
| --- | --- |
| `app/` | 页面（React + Leaflet + TypeScript，用 Vite 构建） |
| `tools/dssat_summary_to_csv.py` | 把 DSSAT `Summary.OUT` 文件读成一张逐年产量表 |
| `tools/csv_to_data.py` | 把你的表格转成页面数据，并计算评分 |
| `tools/check_data.py` | 发布前检查数据 |
| `tools/status_writer.py` | 每 60 秒写出运行状态 |
| `tools/serve.py` | 在本机按正确的响应头提供页面和数据 |
| `tools/make_example_data.py` | 生成虚构的示例数据 |
| `docs/TUTORIAL.zh.md` | 从空电脑到页面和卡片上线的每一步 |
| `docs/DATA_FORMAT.md` | 页面读取的全部文件和字段，以及评分的计算方法 |
| `docs/HOSTING.md` | 获得公开地址的几种方式，以及响应头 |
| `docs/GLOBAL_RUNS_FEED.md` | 全球运行页面上的卡片读取什么，以及状态规则 |
| `docs/STYLE.md` | 哪些要保留、哪些可以改、用词，以及可公开的内容 |
| `docs/CHECKLIST.md` | 上线前最后的检查 |

说明：教程有中文版，其他文档正文为英文；字段名和命令可直接照用。用词要求：KI agents 译为“知识基础设施智能体”；
calibrate 译为“率定”，不用“拟合”。

## 规则摘要

- 只显示真实结果。只有进程确实存在且在工作时才写“正在运行”（状态写出脚本会做到这一点）。
- 页面一上线，`data/` 下的数据就是公开的。不能公开的内容不要放进去。
- 保留页头、颜色和返回按钮，让每个全球运行页面看起来是一家。
- 隧道密钥绝不写进代码、聊天或仓库。

## 已知限制

- `serve.py` 不会沿链接跑出站点文件夹，但如果在请求的那一刻路径上的某个文件夹被换成链接，它发现不了。不要让其他用户
  写入站点文件夹。
- 冬季作物某个失败的生长季如果既没有收获日期也没有成熟日期，会被记在播种那一年；如果同一年还有收获的正常生长季，
  DSSAT 读取工具会把这一年留空（并给出警告），不会猜测。
- 手工修改（不是由 `csv_to_data.py` 写出）的数据文件在页面上仍可能显示异常；`check_data.py` 能发现大部分这类错误。
- 浏览器标签页休眠超过半小时后，某个网格可能暂时显示“无法读取”，页面重新读取清单（2 分钟内）后恢复。
- 页面需要 JavaScript 和近几年的浏览器。

问题：请在本仓库提交 issue。
