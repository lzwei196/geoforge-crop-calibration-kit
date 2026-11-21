# 教程：从你的运行到 GeoForge 全球运行上的实时页面

本教程一步一步带你完成全部工作：从一台空电脑开始，到你的页面上线，并在
[geoforgehhu.com/cn/global-runs.html](https://geoforgehhu.com/cn/global-runs.html) 上有一张卡片。示例是网格化的 DSSAT
率定：规则网格上的一个个网格，以及带统计产量的单元（省、县），每个单元在自己的率定年份上率定，并在验证年份上检验。
English: [TUTORIAL.md](TUTORIAL.md)。

## 一张图看懂

```
运行所在的电脑
  你的运行 ──(表格、Summary.OUT)──> csv_to_data.py ──> site/data/   地图数据       （第 8 步，之后每小时）
  你的运行 ──(PID、日志)──> status_writer.py ──> site/data/runs/  “是否正在运行”   （第 10 步，每 60 秒）
  serve.py      只在 127.0.0.1 上提供 site/（页面 + data/）                    （第 9 步）
  cloudflared   通过隧道把页面送出去                                           （第 11 步）
                                │
                                ▼
            https://<名称>.geoforgehhu.com             你的页面，所有人可访问
                                ▲
                                │ 读取 data/manifest.json 和 data/runs/*/live.json
            geoforgehhu.com/cn/global-runs.html        你的卡片（第 13 步）
```

- 你的运行不会被改动：这些工具只读取它的文件。
- 外部无法访问运行所在的电脑。隧道由这台电脑向外连接到 Cloudflare，Cloudflare 在公开地址上显示你的页面。
  不需要公网 IP、开放端口、域名或证书。
- GeoForge 为你建好地址并发给你隧道密钥。其他方式（自己的域名、自己的网站服务器）见 `HOSTING.md`。

分两部分：

| 部分 | 在哪里 | 步骤 | 时间 |
| --- | --- | --- | --- |
| A. 做页面 | 你自己的电脑（笔记本即可） | 1–7 | 约一天 |
| B. 上线 | 运行所在的电脑 | 8–13 | 约一小时 |

## 开始之前

| 需要 | 在哪台电脑 | 检查方法 |
| --- | --- | --- |
| Python 3.8 或更新（只用标准库） | 两台都要 | `python3 --version` |
| Node.js 18 或更新（只在构建页面时需要） | 你自己的电脑 | `node --version` |
| git | 两台都要 | `git --version` |
| 能向外连接 Cloudflare 的 7844 端口 | 运行所在的电脑 | 检查方法见第 11 步 |
| sudo 权限、systemd | 运行所在的电脑 | 用来启动三个小服务 |

# A 部分：做页面（你自己的电脑）

## 第 1 步：获取工具包

工具包是 GitHub 上的公开仓库：

```
git clone https://github.com/lzwei196/geoforge-crop-calibration-kit.git
cd geoforge-crop-calibration-kit
```

## 第 2 步：试运行示例

```
python3 tools/make_example_data.py
(cd app && npm ci && npm run dev)
```

打开 http://127.0.0.1:8870/ 看一看：

- 黄色的“示例数据”横幅（6 个单元及其产量全是虚构的）；
- 每个网格是一个方块，按率定后产量着色；尚未率定的单元颜色变淡；
- 左上角的图层框（颜色 = 数值）：可按**率定状态**、种植面积、产量，或单元的产量比和 R 着色，并可在雨养和灌溉之间切换；
- 点击一个网格：查看它每年的模拟产量（率定后和率定前），率定年份和验证年份用浅色底标出；
- 右侧的单元：统计产量（白点，灰点 = 不可用）与模拟产量的对比、最终参数和评分；“Example Southeast”（示例东南）
  未纳入，并说明了原因；
- **全部单元**表格：按某一列排序、筛选，点击一行会把地图缩放到该单元；
- 语言按钮：所有文字都会切换，包括 `texts.json` 里的文字；
- 状态标签一开始显示“正在运行”，3 分钟后显示“状态未知（数据暂停更新）”：没有程序持续写示例的状态。
  这正是如实状态规则在起作用，不是故障。

按 Ctrl+C 停止开发服务器。生成页面所用的示例表格在 `example_tables/`，用编辑器或电子表格打开看看。
第 4 步会从你的运行做出同样的六个文件。

## 第 3 步：写好你的文字

复制示例的文字文件，然后改掉每一行：

```
mkdir -p my_tables
cp example_tables/texts.json my_tables/
```

在 `my_tables/texts.json` 中：

- **删除 `"example": true` 这一行；**
- `project_id`：与 GeoForge 商定的简短编号，例如 `cn-wheat-calibration`；
- `map_url`：你的页面地址。第 11 步才会拿到；在那之前保留示例中的地址（必须是 https 地址），到时再改；
- `group`、`title`、`text`（两句话）、`tags`：你的项目，中英文都要写；
- `facts`：保留 `"auto"`（工具会写出“120 / 312 个单元已率定”、网格数和年份），或自己写最多 4 条，每条最多 40 个字符；
- `runs`：你的运行，`run_id`（字母、数字、`_`、`-`）在整个运行期间保持不变；
- `page.crop`、`page.model`（例如“DSSAT 4.8 CERES-Wheat”）、`page.region`、`page.method`（用两三句平实的话说明率定
  怎么做）、`page.reported_source`（统计产量从哪里来）、`page.unit_word`（例如 "province" / "省"）；
- `page.grid_deg`：网格大小（度）；`page.years`：模型运行的第一年和最后一年；
- `page.water`：你的水分条件（例如 `rf` 雨养、`ir` 灌溉），或只有一种 `all`；
- `page.settings`：率定选出的参数，每个写上平实的名称、单位和说明（例如 `G2`，“每株最多籽粒数”，“粒”）。
  只显示这里列出的参数。

用平实的词：说“率定”，不说“拟合”；留出来检验结果的年份叫“验证年份”。更多见 `STYLE.md`。

## 第 4 步：把运行结果转成页面数据

页面由同一个文件夹（`my_tables/`）里的六个文件生成。第一个是你的文字（第 3 步）；另外五个是你的运行已经以某种形式
有的表格。准确的列名见下表和示例文件。“无数值”就写空，绝不要写 -99。

| 文件 | 每行是 | 列 |
| --- | --- | --- |
| `units.csv` | 一个单元 | `unit_id, name_en, name_zh, parent_en, parent_zh, state, cal_start, cal_end, val_start, val_end, note_en, note_zh, progress_done, progress_total` |
| `cells.csv` | 一个网格的一种水分条件 | `cell_id, water, lat, lon, unit_id, area_ha, state` |
| `reported.csv` | 一个单元的一年 | `unit_id, year, yield_t_ha, usable` |
| `model_years.csv` | 一个网格、一种水分条件、一条线的一年 | `cell_id, water, which, year, yield_t_ha` |
| `final_settings.csv` | 一个已率定的单元 | `unit_id`，然后每个 `page.settings` 编号一列 |

各列的意思：

- `units.csv` 的 `state`：`waiting`（等待中）、`calibrating`（正在率定）、`calibrated`（已率定）或 `left_out`（未纳入）。
  已率定的单元必须在 `final_settings.csv` 中有一行。`cal_start`–`cal_end` 和 `val_start`–`val_end` 是该单元自己的
  年份（没有验证年份就把 `val_*` 留空）。`note_*`：读者应知道的一句平实的话，例如“未纳入：统计年份少于 2 年”。
  `progress_*`：单元率定期间已完成和计划的轮数。
- `cells.csv` 的 `lat`、`lon`：网格中心。`area_ha`：该网格这种水分条件的种植面积。`state`：`waiting`、`calibrated`、
  `left_out`（未运行）或 `no_season`（已运行，但任何年份都没有完整生长季：作物无法成熟，例如太冷）。这样的网格在
  `model_years.csv` 中为 0 或空的行会被忽略（DSSAT 读取工具会把失败的生长季写成 0）；如果它有大于 0 的产量，导出会
  停止，因为那说明这个网格其实有生长季。
- `reported.csv` 的 `usable`：你不信任的统计年份（序列断点、已知错误）写 `false`。它会画成灰色，并且不参与评分。
- `model_years.csv` 的 `which`：`uncalibrated`（率定前，初始参数）或 `calibrated`（率定后，单元的最终参数）。
  运行了但没有籽粒的生长季写 `0`；没有运行的年份留空。

**从 DSSAT 输出读取。** `model_years.csv` 可以直接从你的 `Summary.OUT` 文件读出。把它们列在一个索引文件里，
每个网格、每种水分条件、每条线一行：

```
cell_id,water,which,path
N36E117a,rf,uncalibrated,/data/run/base/N36E117a_rf/Summary.OUT
N36E117a,rf,calibrated,/data/run/final/N36E117a_rf/Summary.OUT
```

```
python3 tools/dssat_summary_to_csv.py --index my_index.csv --crop WH --first-year 2010 --last-year 2024 --out my_tables/model_years.csv
```

- `--crop`：`CR` 列中的 DSSAT 作物代码（`MZ` 玉米、`WH` 小麦、`RI` 水稻、`SB` 大豆……）；轮作序列中的休耕和其他作物会被跳过。
- `--first-year`、`--last-year`：只保留这些年份的生长季（用 `page.years`）。DSSAT 序列运行常从预热年份开始，例如 1976 年，
  页面不显示这些年份。
- `--year-from harvest`（默认）把每个生长季记在收获那一年，与大多数产量统计一致；没有收获日期时用成熟日期，再没有就用
  播种日期。`--year-from planting` 用播种年份。
- 产量无法读取的行（空白、`****`、-99 以外的负数）会被跳过并计数，绝不会变成 0。
- 还不存在的文件（尚未率定的单元）计为“尚未生成”；文件存在但无法读取时，工具报错退出，这样后面的导出不会用坏表格运行。
- 已播种但 `HWAM` 为 -99（作物失败）的生长季写成 `0`；用 `--failed missing` 则留空。
- 如果一个文件在同一年有两个生长季，这一年留空，工具会提醒你：它从不猜测。

然后生成数据：

```
python3 tools/csv_to_data.py --tables my_tables --out my_data --dry-run     # checks only, writes nothing
python3 tools/csv_to_data.py --tables my_tables --out my_data
```

第一行只检查，不写任何文件。它还会按同样的方法算出页面要显示的内容（详见 `DATA_FORMAT.md`）：

- 每个单元每年的模拟产量：其网格按种植面积加权的平均值；只有有数值的网格占其计入网格种植面积的至少 90 % 时才计算
  （未纳入或无完整生长季的网格不计入，所以不会把它拉到 90 % 以下）；
- 每个已率定单元在率定年份和验证年份的评分：**产量比**（可用年份上模拟平均值 ÷ 统计平均值；1 = 水平一致）和
  **R**（模拟与统计是否同升同降）；
- 每个网格的地图数值。

所以你不需要自己算评分，页面和数字永远一致。如果你自己的率定用的是别的评分，请在 `page.method` 中说明。

## 第 5 步：检查数据

```
python3 tools/check_data.py my_data
```

它检查每个文件，并根据文件重新算一遍数字。把它列出的错误全部改掉；没有错误时，最后会显示“ready to publish”。
（在第 10 步之前，出现 `live.json: missing` 是正常的。）

## 第 6 步：查看你自己的数据

```
rm -rf app/public/data && cp -r my_data app/public/data
(cd app && npm run dev)
```

再次打开 http://127.0.0.1:8870/。检查：

- 网格出现在你的作物所在的位置（地图会自动缩放到它们）；
- 点击不同单元里的几个网格：种植面积、逐年曲线和浅色底标出的年份都对；
- 从表格打开几个单元：统计产量、最终参数和评分与你的运行一致；
- 等待中或未纳入的单元有说明，说明读起来通顺；
- 切换到 EN，再把所有文字读一遍；
- 把窗口拉窄（约 390 像素，像手机一样）：所有功能仍然可用。

页面代码中哪些可以改、哪些必须保留，见 `STYLE.md`（保留页头、颜色和状态规则）。

## 第 7 步：构建页面

```
(cd app && npm run build)
```

这会生成 `app/dist/`（`index.html` 和 `assets/`）。只有页面代码改变时才需要重新构建，数据改变不需要。

# B 部分：上线（运行所在的电脑）

下面的例子中，运行所有程序的用户是 `crop`，运行文件夹是 `/data/run`，表格在 `/data/out/tables`，运行名为
`cn_wheat_2026_11`。请换成你自己的。如果你的运行在计算集群上，或页面要放在另一台电脑上，请先阅读 `HOSTING.md` 中的
“When the run is on another computer”一节。

## 第 8 步：建好站点文件夹

建好两个文件夹：工具包和站点（页面加数据），并把工具包放进去：

```
sudo mkdir -p /opt/geoforge-crop-kit /opt/geoforge-site
sudo chown crop /opt/geoforge-crop-kit /opt/geoforge-site
git clone https://github.com/lzwei196/geoforge-crop-calibration-kit.git /opt/geoforge-crop-kit
```

如果这台电脑连不上 GitHub，可以从你自己的电脑复制工具包：
`rsync -a --exclude node_modules ./ crop@run-computer:/opt/geoforge-crop-kit/`。

从你自己的电脑复制：构建好的页面放进站点文件夹，你的文字文件放到运行的表格旁边。

```
rsync -a app/dist/ crop@run-computer:/opt/geoforge-site/
scp my_tables/texts.json crop@run-computer:/data/out/tables/
```

你的运行在这台电脑上写出五个表格（第 4 步），这里放在 `/data/out/tables/`（如果要读 `Summary.OUT` 文件，先在这里
运行 `dssat_summary_to_csv.py`）。写出一次数据并检查：

```
cd /opt/geoforge-crop-kit
python3 tools/csv_to_data.py --tables /data/out/tables --out /opt/geoforge-site/data
python3 tools/check_data.py /opt/geoforge-site/data
```

现在只应出现 `live.json: missing` 这一个错误；第 10 步会解决它。

## 第 9 步：启动页面服务

`tools/serve.py` 按正确的响应头提供站点文件夹，只在本机（`127.0.0.1`，端口 8871）。先试一下：

```
python3 tools/serve.py --site /opt/geoforge-site
curl -sI http://127.0.0.1:8871/data/manifest.json        # in a second terminal: must say 200
```

第二行在第二个终端里运行，必须显示 200。按 Ctrl+C 停止，再把它做成服务，每次重启后自动运行。保存为
`/etc/systemd/system/geoforge-site.service`：

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

## 第 10 步：启动状态写出脚本

状态写出脚本告诉读者和全球运行卡片：你的运行是否真的在工作。它必须和运行进程在同一台电脑上，因为它按进程号检查
进程。它需要运行提供两样东西：

- **PID 文件**：记录运行进程号的文件。如果你的运行不写这个文件，可以这样启动：
  `nohup python3 run_calibration.py > run.log 2>&1 & echo $! > run.pid`
- **活动文件**：运行工作时不断写入的日志文件（这里是 `run.log`）。用文件，不要用大文件夹。

先试一下（它每 60 秒写一次，直到按 Ctrl+C）：

```
python3 tools/status_writer.py --data /opt/geoforge-site/data --run-id cn_wheat_2026_11 \
    --pid-file /data/run/run.pid --activity /data/run/run.log \
    --step-en "calibration" --step-zh "率定"
```

在第二个终端里查看 `/opt/geoforge-site/data/runs/cn_wheat_2026_11/live.json`：只有运行进程存在时，`status` 才是 `running`。

**进度：**要显示“120 / 312 个单元已率定”，修改 `tools/status_writer.py` 中的 `progress()` 函数，统计已完成的部分，
例如结果文件的数量：

```python
def progress():
    done = len(list(Path("/data/run/final_settings").glob("*.json")))   # one file per calibrated unit
    return {"done": done, "total": 312, "what": {"en": "units calibrated", "zh": "个单元已率定"}}
```

（这里每个已率定的单元对应一个文件。）做成服务。保存为 `/etc/systemd/system/geoforge-status.service`：

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

**运行结束或暂停时，**要自己写明；进程消失只代表“已停止”：

- **已完成：**先彻底关闭服务（否则下次重启后它会再启动，用“已停止”覆盖“已完成”），再写一次 `finished`：

  ```
  sudo systemctl disable --now geoforge-status
  python3 tools/status_writer.py --data /opt/geoforge-site/data --run-id cn_wheat_2026_11 --pid-file /data/run/run.pid --activity /data/run/run.log --status finished
  ```

- **暂停：**在服务的 `ExecStart` 行加上 `--status paused --note-en "Waiting for new yield statistics" --note-zh "等待新的统计产量"`，
  然后运行 `sudo systemctl daemon-reload && sudo systemctl restart geoforge-status`。运行继续时再去掉
  （同样 reload、restart）。

## 第 11 步：获得公开地址

1. 联系 GeoForge（在本仓库提交 issue，或按约定方式），说明你的 `project_id` 并申请地址。我们会建一个类似
   `https://cn-wheat.geoforgehhu.com` 的地址，并私下把隧道密钥发给你。
2. 检查这台电脑能否连到 Cloudflare 的隧道端口（向外的 TCP 和 UDP 7844 端口；没有任何连接进来）：

   ```
   nc -vz region1.v2.argotunnel.com 7844        # must say "succeeded" or "open"
   ```

   必须显示 “succeeded” 或 “open”。（如果没有 `nc`：`sudo apt install netcat-openbsd`。）

   如果失败，请网络管理员放行到 Cloudflare 7844 端口的向外连接。
3. 安装 `cloudflared` 2025.4 或更新版本。在中国大陆从 GitHub 下载可能很慢，可以先在你自己的电脑上下载，再复制过去
   （ARM 电脑用 `cloudflared-linux-arm64.deb`；其他系统见
   [下载页面](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/)）：

   ```
   curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
   scp cloudflared.deb crop@run-computer:
   ```

   然后在运行所在的电脑上：`sudo dpkg -i cloudflared.deb && cloudflared --version`。
4. 把密钥存进只有 root 能读的文件。绝不要把密钥写在命令行里，这台电脑的其他用户可能看到：

   ```
   sudo mkdir -p /etc/cloudflared
   sudo sh -c 'umask 077; read -r k; printf %s "$k" > /etc/cloudflared/geoforge.token'    # paste the key, press Enter
   ```

   运行第二行后粘贴密钥，按回车。
5. 把隧道做成服务。保存为 `/etc/systemd/system/geoforge-tunnel.service`：

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

   状态应显示 “active (running)”；日志中有 “Registered tunnel connection”。
6. 在浏览器中打开你的地址：页面就出现了。

请保管好密钥：不要写进代码、聊天或仓库。如果泄露，请告诉我们；我们会换一个新的，旧的随即失效。想用自己的域名或
网站服务器：见 `HOSTING.md` 的方式 2 和方式 3。如果第 3 步（写文字）时还不知道地址，现在把它填入 `texts.json` 的
`map_url`，再运行一次导出（第 8 步）。

## 第 12 步：从外部检查

在任意另一台电脑上：

```
curl -sI -H "Origin: https://geoforgehhu.com" https://cn-wheat.geoforgehhu.com/data/manifest.json
```

必须显示 `200`、`Access-Control-Allow-Origin: https://geoforgehhu.com` 和 `Cache-Control: no-store`。在运行所在的电脑上，
`python3 tools/check_data.py /opt/geoforge-site/data` 现在必须显示“ready to publish”。用手机打开页面看看。
然后对照 `CHECKLIST.md` 逐项打勾。

## 第 13 步：加入全球运行

发给 GeoForge：

1. 页面地址和 `project_id`；
2. 一张卡片图片：JPG，1200 × 800 像素，小于 300 KB，图上不要有文字（地图截图效果很好）；
3. 中英文卡片文字：标题（最多 80 个字符）、两句话、最多 6 个标签；
4. 一个处理状态问题的联系人（我们不会公开）。

之后的流程：

1. 我们读取你的文件一天，确认状态持续更新、如实。
2. 我们给你看中英文两种卡片，商定用词。
3. 我们加上卡片并通知你已上线。卡片显示前 3 条 `facts` 和各运行的状态，从你的地址读取；
   图片、标题、文字、标签和按钮地址按商定的保留（需要修改请告诉我们）。

当所有运行都是 `finished`，你的卡片会自动移到“已完成”部分。要下线卡片，把所有运行设为 `finished` 或 `stopped`
并通知我们，当天即可移除。

# 上线之后

## 运行进行中

有新结果时，再运行一次导出，例如用 cron 每小时一次（用 `crop` 用户，`crontab -e`）：

```
0 * * * *  cd /opt/geoforge-crop-kit && flock -n /tmp/geoforge-export.lock sh -c 'python3 tools/dssat_summary_to_csv.py --index /data/out/my_index.csv --crop WH --first-year 2010 --last-year 2024 --out /data/out/tables/model_years.csv && python3 tools/csv_to_data.py --tables /data/out/tables --out /opt/geoforge-site/data' >> /tmp/geoforge-export.log 2>&1
```

- 先重新读取 `Summary.OUT` 文件（新的生长季才能进来），只有这一步成功才会导出数据。如果你的运行自己写
  `model_years.csv`，就去掉前一半。
- 使用与第 4 步相同的 `--crop`、`--year-from` 和 `--failed` 选项，让每小时的运行用同样的方式读取文件。
- 上一次导出还没结束时，`flock` 会跳过这一轮。
- 如果没有任何变化，导出不写任何文件，已打开的页面也不会重新下载全部数据。
- 请让数据流程写完每个 CSV 后再让导出读取（先写临时文件名，再改名）。
- 已打开的页面会在 2 分钟内读到新数据（它们会查看 `data_version` 是否变化）。状态写出脚本会自己继续运行。

新的运行（例如全球运行）：把它加在 `texts.json` 中 `runs` 的最前面，重新导出，再用新的 `--run-id`
建第二个状态写出服务。

## 从一个国家扩展到全球

不需要改代码。把新的单元、网格和年份加进你的表格。注意：

- 单个 `cell_years` 文件保持在约 20 MB 以下；如果一个 5° 方格太大，把 `page.cell_years.tile_deg` 设为 2 或 1；
- 每个访问者都会读取 `cells.json`：约 200,000 行网格（约 30 MB，压缩后 5 MB）没有问题；超过之前请先告诉我们；
- 有自己率定年份和验证年份的单元保持不变（`units.csv` 中的 `cal_*`、`val_*`）。

## 获取 GeoForge 的修复

我们会把修复推送到本仓库。在你自己的电脑上：

```
git pull
cat CHANGELOG.md                     # what changed
(cd app && npm ci && npm run build)
rsync -a app/dist/ crop@run-computer:/opt/geoforge-site/     # never add --delete: it would delete data/
```

`CHANGELOG.md` 记录改了什么。复制页面时绝不要加 `--delete`：它会删掉 `data/`。

在运行所在的电脑上，用 `cd /opt/geoforge-crop-kit && git pull` 更新工具。如果你在第 10 步改过 `progress()`，
让 git 先把你的修改放到一边，更新后再放回：`git stash && git pull && git stash pop`。然后运行
`sudo systemctl restart geoforge-site`；只有运行还在进行时才运行 `sudo systemctl restart geoforge-status`（写了 `finished` 之后再重启，
它会又写成“已停止”）。`git pull` 不会改动你的数据和表格。

## 出问题时

| 你看到 | 可能原因 | 处理 |
| --- | --- | --- |
| 地址上出现 Cloudflare “Error 1033” | 隧道没有连上 | `systemctl status geoforge-tunnel`；做第 11 步的 7844 端口检查 |
| Cloudflare “502 Bad Gateway” | 隧道正常，但页面服务没有响应 | `systemctl status geoforge-site`；`curl -sI http://127.0.0.1:8871/` |
| “状态未知（数据暂停更新）” | `live.json` 超过 3 分钟没有更新 | `systemctl status geoforge-status`；检查时钟是否同步（NTP） |
| 运行在工作却显示“已停止” | PID 文件里的进程号不是运行进程 | 写入真正运行进程的 PID（不是一个启动后就退出的外壳进程） |
| 运行结束后仍显示“正在运行” | 旧 PID 文件的进程号被别的进程用了 | 运行结束时删除 PID 文件；写 `finished`（第 10 步） |
| 页面提示无法读取数据 | 还没有 `data/`，或文件损坏 | 运行导出（第 8 步）和 `check_data.py` |
| 全球运行卡片上没有状态 | 浏览器无法从 geoforgehhu.com 读取你的文件 | 第 12 步的 `curl` 必须显示 `Access-Control-Allow-Origin` 那一行 |
| 新数据没有出现 | 导出失败，或没有发现新内容 | 查看 `/tmp/geoforge-export.log` |
| 某个网格显示 0，但应为空 | 没有运行的年份被写成了 0 | 在 `model_years.csv` 中留空；只有没有籽粒的生长季才是 0 |
| 某个单元没有验证评分 | 验证年份中可用的统计年份少于 2 年 | 这是正确的；在它的 `note_en` / `note_zh` 中说明原因 |
| 已率定的单元没有模拟曲线 | 这些年份中有数值的网格不到其计入种植面积的 90 % | 检查 `model_years.csv` 中缺失的年份；作物无法成熟的网格应在 `cells.csv` 中写 `no_season` |

其他问题：请在本仓库提交 issue。
