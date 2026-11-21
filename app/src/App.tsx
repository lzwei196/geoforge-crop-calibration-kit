import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CALIBRATED, LEFT_OUT, WAITING, clearTiles, getJSON, loadCellYears, validCells, validLive, validManifest, validUnits, vpath, type Cells, type Live, type Manifest, type Unit, type Units } from './api'
import { firstLang, hubUrl, saveLang, tr, words, type Lang } from './i18n'
import { NO_VALUE, RANK, STATE_COLORS, divColor, fmt, isRatio, range, ratioText, seqColor, stateOf, when } from './format'
import { MapView } from './MapView'
import { CellPanel, ProjectPanel, ResultsPanel, UnitPanel, type YearsLoad } from './Panels'

const LIVE_EVERY_MS = 30_000          // run status (live.json): every 30 s
const DATA_EVERY_MS = 120_000         // manifest.json: every 2 min; the other files are read again only when updated_at changes
const STATE_ID = '__state'            // the built-in "Calibration state" colour

class Guard extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: Error) { return { err: e.message } }
  render() { return this.state.err ? <div className="empty error">{this.state.err}</div> : this.props.children }
}

// a cell whose unit is not calibrated yet is drawn washed out, so finished and unfinished areas are easy to tell apart
function fade(c: string): string {
  if (c.startsWith('rgb(')) return c.replace('rgb(', 'rgba(').replace(')', ',.35)')
  if (c.startsWith('#') && c.length === 7) return `rgba(${parseInt(c.slice(1, 3), 16)},${parseInt(c.slice(3, 5), 16)},${parseInt(c.slice(5, 7), 16)},.35)`
  return c
}

export default function App() {
  const [lang, setLang] = useState<Lang>(firstLang)
  const w = words(lang)
  const [m, setM] = useState<Manifest | null>(null)
  const [cells, setCells] = useState<Cells | null>(null)
  const [units, setUnits] = useState<Unit[] | null>(null)
  const [lives, setLives] = useState<Record<string, Live | null>>({})
  const [err, setErr] = useState<string | null>(null)
  const [dataErr, setDataErr] = useState<string | null>(null)      // newer data could not be read: the page keeps the last good set
  const [valueId, setValueId] = useState<string | null>(null)
  const [water, setWater] = useState<string | null>(null)
  const [selCell, setSelCell] = useState<{ id: string; water: string } | null>(null)   // by id: rows change between updates
  const [unitId, setUnitId] = useState<string | null>(null)
  const [years, setYears] = useState<Record<string, YearsLoad>>({})                    // "<cell id>|<water>"
  const [hover, setHover] = useState<{ row: number; x: number; y: number } | null>(null)
  const [focus, setFocus] = useState<{ bounds: [[number, number], [number, number]]; token: number } | null>(null)
  const [q, setQ] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())
  const cellRef = useRef<HTMLDivElement>(null)
  const unitRef = useRef<HTMLDivElement>(null)
  const shown = useRef<string | null>(null)                    // data_version on screen
  const busy = useRef(false)                                   // one data read at a time (a slow link must not stack them)
  const liveSeq = useRef<Record<string, { asked: number; shown: number }>>({})   // per run: newest request, newest answer shown

  useEffect(() => { document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'; saveLang(lang) }, [lang])
  useEffect(() => { if (m) document.title = `${tr(m.title, lang)} · GeoForge Global Runs` }, [m, lang])

  // data: manifest every 2 min; when its data_version changed, read that version's cells + units and show the three
  // together. If the new files cannot be read, keep showing the last good set and say so.
  const loadData = useCallback(() => {
    if (busy.current) return
    busy.current = true
    getJSON<unknown>('manifest.json').then(mm => {
      if (!validManifest(mm)) throw new Error('manifest.json: not in the expected shape')
      if (shown.current === mm.data_version) { setM(mm); setErr(null); setDataErr(null); return }
      const ver = mm.data_version
      return Promise.all([getJSON<unknown>(vpath(ver, 'cells.json')), getJSON<unknown>(vpath(ver, 'units.json'))]).then(([c, u]) => {
        if (!validCells(c)) throw new Error(`${vpath(ver, 'cells.json')}: not in the expected shape`)
        if (!validUnits(u)) throw new Error(`${vpath(ver, 'units.json')}: not in the expected shape`)
        shown.current = ver; clearTiles(); setYears({})
        setM(mm); setCells(c); setUnits(u.units); setErr(null); setDataErr(null)
        setValueId(v => v && (v === STATE_ID || mm.page.values.some(x => x.id === v)) ? v : mm.page.default_value)
        setWater(x => x && mm.page.water.some(o => o.id === x) ? x : mm.page.water[0]?.id ?? null)
      })
    }).catch(e => { const t = String(e?.message || e); if (shown.current) setDataErr(t); else setErr(t) })
      .finally(() => { busy.current = false })
  }, [])
  useEffect(() => { loadData(); const t = setInterval(loadData, DATA_EVERY_MS); return () => clearInterval(t) }, [loadData])

  // run status: every 30 s; a run without a readable file shows "no status" (never "running")
  const runIds = m?.runs.map(r => r.run_id).join('|') ?? ''
  useEffect(() => {
    if (!runIds) return
    // each run on its own: a slow run never holds back the others, and an older answer never replaces a newer one
    const read = () => runIds.split('|').forEach(id => {
      const s = liveSeq.current[id] ??= { asked: 0, shown: 0 }
      const seq = ++s.asked
      getJSON<unknown>(`runs/${encodeURIComponent(id)}/live.json`, 20_000).catch(() => null).then(l => {
        if (seq <= s.shown) return
        s.shown = seq
        setLives(v => ({ ...v, [id]: validLive(l, id) })); setNow(Date.now())
      })
    })
    read(); const t = setInterval(read, LIVE_EVERY_MS); return () => clearInterval(t)
  }, [runIds])
  useEffect(() => { setLives(v => Object.fromEntries(runIds.split('|').filter(Boolean).map(id => [id, v[id] ?? null]))) }, [runIds])
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 15_000); return () => clearInterval(t) }, [])

  const unitById = useMemo(() => new Map((units ?? []).map(u => [u.id, u])), [units])
  const rows = useMemo(() => { const out: number[] = []; if (cells && water) cells.water.forEach((x, k) => { if (x === water) out.push(k) }); return out }, [cells, water])
  const cellCount = useMemo(() => { const c: Record<string, number> = {}; const seen = new Set<string>()
    if (cells) cells.id.forEach((id, k) => { const key = id + '|' + cells.unit[k]; if (!seen.has(key)) { seen.add(key); c[cells.unit[k]] = (c[cells.unit[k]] ?? 0) + 1 } }); return c }, [cells])
  const nCells = useMemo(() => cells ? new Set(cells.id).size : 0, [cells])

  const vdef = m?.page.values.find(v => v.id === valueId) ?? null
  const scale = useMemo(() => {
    if (!cells) return null
    if (valueId === STATE_ID || !vdef) return { colors: rows.map(k => STATE_COLORS[cells.state[k]] ?? NO_VALUE), lo: 0, hi: 0 }
    const vals = cells.values[vdef.id] ?? []
    const div = vdef.scale === 'diverging', [lo, hi] = range(rows.map(k => vals[k] ?? null), div, vdef.center ?? 0), f = div ? divColor : seqColor
    return { colors: rows.map(k => { const v = vals[k]
      if (typeof v !== 'number' || !Number.isFinite(v)) return NO_VALUE
      const c = f((v - lo) / (hi - lo)); return cells.state[k] === WAITING ? fade(c) : c }), lo, hi }
  }, [cells, rows, vdef, valueId])

  // the open cell: every water kind at this place, the one picked first
  const selRows = useMemo(() => {
    if (!cells || !selCell) return []
    const out: number[] = []
    cells.id.forEach((id, k) => { if (id === selCell.id) out.push(k) })
    return out.sort((a, b) => (cells.water[a] === selCell.water ? -1 : 0) - (cells.water[b] === selCell.water ? -1 : 0))
  }, [cells, selCell])
  const selRow = selRows[0] ?? null
  // read the yearly values of the open cell (again after a data update cleared them)
  useEffect(() => {
    if (!cells || !m) return
    const ver = m.data_version
    for (const k of selRows) {
      const key = `${ver}|${cells.id[k]}|${cells.water[k]}`        // with the version: an answer for old data never shows on new data
      if (years[key] !== undefined) continue
      setYears(y => ({ ...y, [key]: 'loading' }))
      loadCellYears(ver, cells.id[k], cells.water[k], cells.lat[k], cells.lon[k], m.page.cell_years.tile_deg)
        .then(r => setYears(y => ({ ...y, [key]: r }))).catch(() => setYears(y => ({ ...y, [key]: 'error' })))
    }
  }, [selRows, years, cells, m])
  // a cell or unit that is gone after an update is closed
  useEffect(() => { if (cells && selCell && selRows.length === 0) setSelCell(null) }, [cells, selCell, selRows])
  useEffect(() => { if (units && unitId && !unitById.has(unitId)) setUnitId(null) }, [units, unitId, unitById])

  const top = useMemo(() => m ? m.runs.map(r => stateOf(lives[r.run_id] ?? null, w, lang, now)).sort((a, b) => RANK[a.key] - RANK[b.key])[0] ?? null : null, [m, lives, w, lang, now])
  const doneUnits = units ? units.filter(u => u.state === 'calibrated').length : 0

  const say = (t: string) => { setToast(t); setTimeout(() => setToast(null), 3500) }
  const openRow = (k: number | null) => {
    if (k === null || !cells) return
    // a cell whose yearly values failed to load is tried again when it is opened again
    setYears(y => Object.fromEntries(Object.entries(y).filter(([key, v]) => !(v === 'error' && key.split('|')[1] === cells.id[k]))))
    setSelCell({ id: cells.id[k], water: cells.water[k] }); setUnitId(cells.unit[k])
    setWater(cells.water[k])                                     // the map always shows the water kind of the open cell
    setTimeout(() => cellRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }
  const openUnit = (id: string, scroll = true) => {
    if (!cells) return
    setUnitId(id)
    setSelCell(c => c && cells.unit[cells.id.indexOf(c.id)] === id ? c : null)   // a cell of another unit is closed
    let s = 90, n = -90, wst = 180, e = -180, any = false
    cells.unit.forEach((u, k) => { if (u === id) { any = true; s = Math.min(s, cells.lat[k]); n = Math.max(n, cells.lat[k]); wst = Math.min(wst, cells.lon[k]); e = Math.max(e, cells.lon[k]) } })
    const g = m?.page.grid_deg ?? 0.1
    if (any) setFocus({ bounds: [[s - g, wst - g], [n + g, e + g]], token: Date.now() })
    if (scroll) setTimeout(() => unitRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 60)
  }
  const search = () => {
    if (!cells || !units) return
    const t = q.trim(), ll = t.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/)
    if (ll) {                                                    // the nearest cell within 0.5° (the shown water kind first)
      const g = m?.page.grid_deg ?? 0.1, la = +ll[1], lo = +ll[2]
      let k = -1, bd = 0.25 + 1e-9
      for (const pool of [rows, cells.lat.map((_, i) => i)]) {
        for (const i of pool) { const d = (cells.lat[i] - la) ** 2 + (cells.lon[i] - lo) ** 2; if (d < bd) { bd = d; k = i } }
        if (k >= 0) break
      }
      if (k < 0) return say(w.notFound)
      setFocus({ bounds: [[la - g * 20, lo - g * 20], [la + g * 20, lo + g * 20]], token: Date.now() }); return openRow(k)
    }
    if (!t) return
    const low = t.toLowerCase()
    const same = (i: number) => cells.id[i].toLowerCase() === low
    let k = rows.find(same) ?? -1
    if (k < 0) k = cells.id.findIndex((_, i) => same(i))
    if (k >= 0) { const g = m?.page.grid_deg ?? 0.1; setFocus({ bounds: [[cells.lat[k] - g * 20, cells.lon[k] - g * 20], [cells.lat[k] + g * 20, cells.lon[k] + g * 20]], token: Date.now() }); return openRow(k) }
    const u = units.find(x => x.id.toLowerCase() === low) ?? units.find(x => x.name.en.toLowerCase().includes(low) || x.name.zh.includes(t))
    if (!u) return say(w.notFound)
    openUnit(u.id)
  }

  if (err && !m && !shown.current) return <div className="fatal">{w.fatal} {err}</div>
  const unit = unitId ? unitById.get(unitId) : undefined
  const hoverText = (k: number) => {
    if (!cells) return null
    const u = unitById.get(cells.unit[k])
    let v: string
    if (valueId === STATE_ID || !vdef) v = `${w.stateValue}: ${[w.st0, w.st1, w.st2, w.st3][cells.state[k]] ?? '—'}`
    else { const x = cells.values[vdef.id]?.[k] ?? null; v = `${tr(vdef.name, lang)}: ${x === null ? w.noValue : isRatio(vdef) ? ratioText(x, lang) : `${fmt(x, 2, lang)} ${vdef.unit}`}` }
    return <><b>{u ? tr(u.name, lang) : cells.unit[k]}</b> · {cells.id[k]}<br />{v}</>
  }
  return (
    <div className="app">
      <header className="top">
        <a className="back-link" href={hubUrl(lang)}>{w.back}</a>
        <div className="brand"><span className="logo" />{m ? tr(m.title, lang) : '…'}</div>
        <div className="search"><input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()} placeholder={w.search} aria-label={w.search} /><button onClick={search}>{w.go}</button></div>
        <button className="lang-btn" onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}>{w.other}</button>
        <div className={`badge ${top?.key ?? 'unknown'}`}><i />{top ? top.text : m ? w.noStatus : w.loading}</div>
      </header>
      {m?.example && <div className="example-banner">{w.example}</div>}
      {dataErr && <div className="data-banner">{w.dataErr} ({dataErr})</div>}
      <section className="hero">
        <div className="map-wrap">
          {!cells && <div className="map loading">{err ? `${w.fatal} ${err}` : w.loading}</div>}
          <Guard><MapView cells={cells} rows={rows} colors={scale?.colors ?? null} grid={m?.page.grid_deg ?? 0.1} selected={selRow} focus={focus} onPick={openRow} onHover={setHover} /></Guard>
          {m && <div className="map-side"><div className="layer-box">
            <div className="eyebrow">{w.colourBy}</div>
            <select value={valueId ?? ''} onChange={e => setValueId(e.target.value)} aria-label={w.colourBy}>
              <option value={STATE_ID}>{w.stateValue}</option>
              {m.page.values.map(v => <option key={v.id} value={v.id}>{tr(v.name, lang)}</option>)}
            </select>
            {m.page.water.length > 1 && <div className="water-row"><span className="muted small">{w.water}</span>
              <div className="seg">{m.page.water.map(o => <button key={o.id} className={o.id === water ? 'on' : ''} onClick={() => setWater(o.id)}>{tr(o.name, lang)}</button>)}</div></div>}
            {valueId === STATE_ID || !vdef
              ? <div className="legend-cat">{[w.st1, w.st0, w.st3, w.st2].map((t, k) => <span key={k}><i style={{ background: STATE_COLORS[[CALIBRATED, WAITING, 3, LEFT_OUT][k]] }} />{t}</span>)}</div>
              : <>{scale && <div className="legend-seq"><div className="ramp" style={{ background: `linear-gradient(90deg, ${[0, .17, .33, .5, .67, .83, 1].map(vdef.scale === 'diverging' ? divColor : seqColor).join(',')})` }} />
                  <div className="ends"><span>{fmt(scale.lo, 2, lang)}</span><span>{vdef.unit}</span><span>{fmt(scale.hi, 2, lang)}</span></div></div>}
                <div className="legend-row"><i style={{ background: NO_VALUE }} />{w.noValue}</div>
                <div className="legend-row muted small">{w.st0}: {lang === 'zh' ? '颜色变淡' : 'washed-out colour'}</div>
                {vdef.note && <div className="muted small">{tr(vdef.note, lang)}</div>}</>}
          </div></div>}
          {hover && cells && <div className="hover" style={{ left: hover.x + 14, top: hover.y + 14 }}>{hoverText(hover.row)}</div>}
          {toast && <div className="toast" onClick={() => setToast(null)}>{toast}</div>}
        </div>
        <div className="hero-strip">
          <div><b>{units ? `${fmt(doneUnits, 0, lang)} / ${fmt(units.length, 0, lang)}` : '—'}</b><span>{w.calibratedUnits}</span></div>
          <div><b>{fmt(nCells, 0, lang)}</b><span>{w.cells} · {m ? `${m.page.grid_deg}°` : ''}</span></div>
          <div><b>{m ? `${m.page.years[0]}–${m.page.years[1]}` : '—'}</b><span>{w.yearsK}</span></div>
          <div><b>{m ? when(m.updated_at, lang) : '—'}</b><span>{w.updated}</span></div>
          <div className="scroll-hint">{w.clickHint}</div>
        </div>
      </section>
      <main className="body">
        <div className="panel" ref={cellRef}><Guard>
          {selRow !== null && cells && m ? <CellPanel rows={selRows} cells={cells} m={m} unit={unitById.get(cells.unit[selRow])}
              years={Object.fromEntries(selRows.map(k => [k, years[`${m.data_version}|${cells.id[k]}|${cells.water[k]}`] ?? 'loading']))} lang={lang} w={w} />
            : <div className="intro"><div className="eyebrow">{w.introEye}</div><h2>{w.introTitle}</h2><p className="muted">{w.introText}</p></div>}
        </Guard></div>
        <div className="panel" ref={unitRef}><Guard>
          {unit && m ? <UnitPanel u={unit} m={m} nCells={cellCount[unit.id] ?? 0} lang={lang} w={w} />
            : <div className="intro"><div className="eyebrow">{m ? tr(m.page.unit_word, lang) : w.unitEye}</div><h2>{w.unitIntroTitle}</h2><p className="muted">{w.unitIntroText}</p></div>}
        </Guard></div>
        <div className="panel wide"><Guard>{m && units && <ResultsPanel units={units} cellCount={cellCount} m={m} lang={lang} w={w} onOpen={id => openUnit(id)} />}</Guard></div>
        <div className="panel wide"><Guard>{m && <ProjectPanel m={m} lives={lives} lang={lang} w={w} now={now} />}</Guard></div>
      </main>
      <footer className="foot">{m && <>{tr(m.group, lang)} · </>}<a href={hubUrl(lang)}>GeoForge Global Runs</a></footer>
    </div>
  )
}
