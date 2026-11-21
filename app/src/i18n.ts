// Page words in English and Chinese. Texts about YOUR project (title, crop, value names, notes) come from manifest.json.
// Keep the words plain: say what a reader sees. Say "calibrate", never "fit"; data kept out to test is "validation".
import type { L } from './api'

export type Lang = 'en' | 'zh'
const W = {
  en: {
    back: '← Global runs', other: '中文', search: 'Unit name, cell id or “lat, lon”', go: 'Go', loading: 'Loading…',
    fatal: 'The map data could not be read:', example: 'Example data: made up to show how the page works. These are not real results.',
    colourBy: 'Colour = a value', water: 'Water', noValue: 'no value', notFound: 'Nothing found. Try a unit name, a cell id or “lat, lon”.',
    stateValue: 'Calibration state',
    st0: 'waiting', st1: 'calibrated', st2: 'left out (not run)', st3: 'run, but no season (crop never finishes)',
    us_waiting: 'waiting', us_calibrating: 'calibrating now', us_calibrated: 'calibrated', us_left_out: 'left out',
    units: 'units', calibratedUnits: 'units calibrated', cells: 'cells', yearsK: 'model years', updated: 'data updated',
    clickHint: 'Click a cell ↓',
    introEye: 'Cell', introTitle: 'Click a cell on the map', introText: 'A cell shows its crop area and its model yield for every year, before and after calibration.',
    unitIntroTitle: 'Click a cell or a row in the table', unitIntroText: 'A unit shows its reported yields against the model, its final settings and how well they did in calibration and validation years.',
    cellEye: 'Cell', unitEye: 'Unit', area: 'crop area', ha: 'ha', state: 'state', unitK: 'unit',
    calibrated: 'Calibrated', uncalibrated: 'Uncalibrated', reported: 'Reported', notUsable: 'not usable (not scored)',
    calYears: 'Calibration years', valYears: 'Validation years', noValidation: 'no validation years',
    yieldPerYear: 'Model yield per year', unitYield: 'Reported yield and model yield', tha: 't/ha',
    noYears: 'No yearly model values for this cell yet.', yearsErr: 'Could not read this cell’s yearly values.',
    zeroNote: 'season(s) at 0 t/ha (crop failed or gave no grain)', missingNote: 'year(s) with no value',
    finalSettings: 'Final settings', notYet: 'not calibrated yet', scores: 'How well the final settings do',
    part: 'Years', ratio: 'Yield ratio', ratioNote: 'model ÷ reported; 1 = right level', r: 'R', rNote: 'do model and reports rise and fall together? 1 = fully',
    nYears: 'years compared', tooFew: 'too few usable reported years to compare',
    periods: 'Years used', progress: 'progress', otherWater: 'Other water kinds in this cell',
    projectEye: 'The project', by: 'by', crop: 'Crop', model: 'Model', method: 'Method', region: 'Area', source: 'Reported yields from', runs: 'Runs', started: 'started',
    running: 'Running now', paused: 'Paused', stopped: 'Stopped', lastActivity: 'last activity', finished: 'Finished', failed: 'Ended with an error',
    unknown: 'Status unknown (feed paused)', noStatus: 'No status yet', step: 'step', year: 'year',
    resultsEye: 'Results', resultsTitle: 'All units', summaryCal: 'Calibration years', summaryVal: 'Validation years',
    scored: 'units scored', medRatio: 'median yield ratio', within10: 'within ±10 %', medR: 'median R',
    colName: 'Unit', colState: 'State', colCells: 'Cells', showAll: 'Show all', showLess: 'Show fewer', filter: 'Filter units',
    of: 'of',
    dataErr: 'Newer data could not be read; the page still shows the last data it read. It tries again every 2 minutes.',
    noScore: 'cannot be worked out: the reported or model yields are 0 or the same in every year',
  },
  zh: {
    back: '← 全球运行', other: 'EN', search: '单元名称、网格编号或“纬度, 经度”', go: '搜索', loading: '正在加载…',
    fatal: '无法读取地图数据：', example: '示例数据：仅用于展示页面功能，并非真实结果。',
    colourBy: '颜色 = 数值', water: '水分条件', noValue: '无数值', notFound: '没有找到。请输入单元名称、网格编号或“纬度, 经度”。',
    stateValue: '率定状态',
    st0: '等待中', st1: '已率定', st2: '未纳入（未运行）', st3: '已运行，但无完整生长季（作物无法成熟）',
    us_waiting: '等待中', us_calibrating: '正在率定', us_calibrated: '已率定', us_left_out: '未纳入',
    units: '个单元', calibratedUnits: '个单元已率定', cells: '个网格', yearsK: '模拟年份', updated: '数据更新于',
    clickHint: '点击网格 ↓',
    introEye: '网格', introTitle: '点击地图上的网格', introText: '可查看该网格的种植面积，以及率定前后每年的模拟产量。',
    unitIntroTitle: '点击网格或表格中的一行', unitIntroText: '可查看该单元的统计产量与模拟产量对比、最终参数，以及在率定年份和验证年份的表现。',
    cellEye: '网格', unitEye: '单元', area: '种植面积', ha: '公顷', state: '状态', unitK: '单元',
    calibrated: '率定后', uncalibrated: '率定前', reported: '统计产量', notUsable: '不可用（不参与评分）',
    calYears: '率定年份', valYears: '验证年份', noValidation: '无验证年份',
    yieldPerYear: '每年模拟产量', unitYield: '统计产量与模拟产量', tha: '吨/公顷',
    noYears: '该网格暂时没有逐年模拟值。', yearsErr: '无法读取该网格的逐年数值。',
    zeroNote: '个生长季为 0 吨/公顷（作物失败或未结实）', missingNote: '个年份无数值',
    finalSettings: '最终参数', notYet: '尚未率定', scores: '最终参数的表现',
    part: '年份', ratio: '产量比', ratioNote: '模拟 ÷ 统计；1 = 水平一致', r: 'R', rNote: '模拟与统计是否同升同降？1 = 完全一致',
    nYears: '比较年数', tooFew: '可用统计年份太少，无法比较',
    periods: '使用年份', progress: '进度', otherWater: '该网格的其他水分条件',
    projectEye: '项目', by: '来自', crop: '作物', model: '模型', method: '方法', region: '范围', source: '统计产量来源', runs: '运行', started: '开始',
    running: '正在运行', paused: '已暂停', stopped: '已停止', lastActivity: '最近活动', finished: '已完成', failed: '出错结束',
    unknown: '状态未知（数据暂停更新）', noStatus: '暂无状态', step: '步骤', year: '年份',
    resultsEye: '结果', resultsTitle: '全部单元', summaryCal: '率定年份', summaryVal: '验证年份',
    scored: '个单元有评分', medRatio: '产量比中位数', within10: '在 ±10 % 以内', medR: 'R 中位数',
    colName: '单元', colState: '状态', colCells: '网格数', showAll: '显示全部', showLess: '收起', filter: '筛选单元',
    of: '/',
    dataErr: '无法读取更新的数据，页面仍显示上次读到的数据，每 2 分钟重试一次。',
    noScore: '无法计算：统计产量或模拟产量为 0，或每年都相同',
  },
}
export type Words = typeof W.en
export const words = (lang: Lang): Words => W[lang]
export const tr = (l: L | undefined, lang: Lang) => (l ? l[lang] || l.en : '')

// first language: ?lang=zh|en, else ?from=cn (sent by the Chinese Global Runs page), else the reader's last choice, else English
export function firstLang(): Lang {
  const q = new URLSearchParams(window.location.search)
  if (q.get('lang') === 'zh' || q.get('lang') === 'en') return q.get('lang') as Lang
  if (q.get('from') === 'cn') return 'zh'
  try { const s = localStorage.getItem('gr-lang'); if (s === 'zh' || s === 'en') return s } catch { /* storage off */ }
  return 'en'
}
export function saveLang(l: Lang) { try { localStorage.setItem('gr-lang', l) } catch { /* storage off */ } }

// the "back" button always goes to the GeoForge Global Runs page in the page's language
export const hubUrl = (l: Lang) => l === 'zh' ? 'https://geoforgehhu.com/cn/global-runs.html' : 'https://geoforgehhu.com/global-runs.html'
