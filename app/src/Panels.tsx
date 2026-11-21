import { useMemo, useState } from 'react'
import type { Cells, CellYears, Live, Manifest, Score, Unit } from './api'
import type { Lang, Words } from './i18n'
import { tr } from './i18n'
import { YearChart, type Band, type Line } from './Chart'
import { f2, fmt, isRatio, median, ratioText, stateOf, when, STATE_COLORS } from './format'

function Row({ k, v, note }: { k: string; v: React.ReactNode; note?: string }) {
  return <div><dt>{k}</dt><dd>{v}{note && <span className="note">{note}</span>}</dd></div>
}
const stateWord = (s: number, w: Words) => [w.st0, w.st1, w.st2, w.st3][s] ?? '—'
const unitStateWord = (s: Unit['state'], w: Words) => ({ waiting: w.us_waiting, calibrating: w.us_calibrating, calibrated: w.us_calibrated, left_out: w.us_left_out })[s] ?? s
export function UnitPill({ u, w }: { u: Unit; w: Words }) { return <span className={`pill ${u.state}`}>{unitStateWord(u.state, w)}</span> }

function bandsOf(u: Unit | undefined, w: Words): Band[] {
  if (!u) return []
  const b: Band[] = [{ from: u.periods.calibration[0], to: u.periods.calibration[1], label: w.calYears, kind: 'cal' }]
  if (u.periods.validation) b.push({ from: u.periods.validation[0], to: u.periods.validation[1], label: w.valYears, kind: 'val' })
  return b
}
const periodText = (p: [number, number] | null, w: Words) => p ? `${p[0]}–${p[1]}` : w.noValidation

// ---- one cell: every water kind at this place, with its yearly model yield ----------------------------------------
export type YearsLoad = { years: number[]; y: CellYears | null } | 'loading' | 'error'
export function CellPanel({ rows, cells, m, unit, years, lang, w }: {
  rows: number[]                     // cells.json rows of this cell (one per water kind), the clicked one first
  cells: Cells; m: Manifest; unit: Unit | undefined
  years: Record<number, YearsLoad>
  lang: Lang; w: Words
}) {
  const r0 = rows[0]
  const wname = (id: string) => tr(m.page.water.find(x => x.id === id)?.name, lang) || id
  const many = rows.length > 1
  const lines: Line[] = []
  let zeros = 0, missing = 0, loading = false, error = false
  rows.forEach((r, k) => {
    const yl = years[r]
    if (yl === 'loading' || yl === undefined) { loading = true; return }
    if (yl === 'error') { error = true; return }
    if (!yl.y) return
    const sfx = many ? ` · ${wname(cells.water[r])}` : ''
    const cal = yl.y.calibrated, base = yl.y.uncalibrated
    const hasCal = !!cal && cal.some(v => v !== null)
    if (hasCal) lines.push({ id: `c${r}`, label: w.calibrated + sfx, years: yl.years, v: cal!, kind: k ? 'cal2' : 'cal' })
    if (base) lines.push({ id: `b${r}`, label: w.uncalibrated + sfx, years: yl.years, v: base, kind: k ? 'base2' : 'base' })
    const main = hasCal ? cal! : base ?? []
    zeros += main.filter(v => v === 0).length; missing += main.filter(v => v === null).length
  })
  return (
    <>
      <div className="panel-head"><div><div className="eyebrow">{w.cellEye}</div>
        <h2>{cells.id[r0]}<small>{cells.lat[r0].toFixed(3)}°, {cells.lon[r0].toFixed(3)}° · {m.page.grid_deg}°</small></h2></div></div>
      <div className="inputs">
        {rows.map(r => <div key={r} className="card input-card"><div className="card-head"><h3>{wname(cells.water[r])}</h3>
          <span className="source"><i className="sq" style={{ background: STATE_COLORS[cells.state[r]] }} />{stateWord(cells.state[r], w)}</span></div><dl>
          <Row k={w.unitK} v={unit ? tr(unit.name, lang) : cells.unit[r]} />
          <Row k={w.area} v={cells.area_ha[r] === null ? '—' : `${fmt(cells.area_ha[r], 0, lang)} ${w.ha}`} />
          {m.page.values.filter(v => v.id !== 'area_ha').map(v => { const x = cells.values[v.id]?.[r] ?? null
            return <Row key={v.id} k={tr(v.name, lang)} v={x === null ? '—' : isRatio(v) ? ratioText(x, lang) : v.id.startsWith('unit_r_') ? f2(x, lang) : `${fmt(x, 2, lang)} ${v.unit}`.trim()} /> })}
        </dl></div>)}
      </div>
      <div className="card"><div className="card-head"><h3>{w.yieldPerYear}</h3><span className="source">{w.tha}</span></div>
        {loading ? <div className="empty">{w.loading}</div>
          : error && !lines.length ? <div className="empty error">{w.yearsErr}</div>
          : <YearChart lines={lines} bands={bandsOf(unit, w)} unit={w.tha} lang={lang} none={w.noYears} />}
        {!loading && lines.length > 0 && (zeros > 0 || missing > 0) && <div className="muted small">
          {zeros > 0 && <>{fmt(zeros, 0, lang)} {w.zeroNote}. </>}{missing > 0 && <>{fmt(missing, 0, lang)} {w.missingNote}.</>}</div>}
      </div>
    </>
  )
}

// ---- one unit: reported vs model, final settings, scores ---------------------------------------------------------
function ScoreRows({ label, p, s, w, lang }: { label: string; p: [number, number] | null; s: Score | null | undefined; w: Words; lang: Lang }) {
  if (!p) return <tr><td>{label}</td><td colSpan={3} className="muted">{w.noValidation}</td></tr>
  if (!s || s.n < 2) return <tr><td>{label}<div className="muted small">{p[0]}–{p[1]}</div></td><td colSpan={3} className="muted">{w.tooFew}{s ? ` (${s.n})` : ''}</td></tr>
  if (s.ratio === null && s.r === null) return <tr><td>{label}<div className="muted small">{p[0]}–{p[1]}</div></td><td colSpan={2} className="muted">{w.noScore}</td><td>{s.n}</td></tr>
  return <tr><td>{label}<div className="muted small">{p[0]}–{p[1]}</div></td><td>{ratioText(s.ratio, lang)}</td><td>{f2(s.r, lang)}</td><td>{s.n}</td></tr>
}
export function UnitPanel({ u, m, nCells, lang, w }: { u: Unit; m: Manifest; nCells: number; lang: Lang; w: Words }) {
  const unusable = new Set(u.reported.years.filter((_, k) => !u.reported.usable[k]))
  const lines: Line[] = [
    { id: 'rep', label: w.reported, years: u.reported.years, v: u.reported.yield, kind: 'rep' },
    ...(u.model.calibrated.some(v => v !== null) ? [{ id: 'cal', label: w.calibrated, years: u.model.years, v: u.model.calibrated, kind: 'cal' as const }] : []),
    ...(u.model.uncalibrated.some(v => v !== null) ? [{ id: 'base', label: w.uncalibrated, years: u.model.years, v: u.model.uncalibrated, kind: 'base' as const }] : []),
  ]
  const notYet = u.state === 'left_out' ? w.us_left_out : w.notYet
  return (
    <>
      <div className="panel-head"><div><div className="eyebrow">{tr(m.page.unit_word, lang) || w.unitEye}</div>
        <h2>{tr(u.name, lang)}<small>{u.parent ? `${tr(u.parent, lang)} · ` : ''}{u.id} · {fmt(nCells, 0, lang)} {w.cells}</small></h2></div>
        <UnitPill u={u} w={w} /></div>
      {u.note && <p className="note-line">{tr(u.note, lang)}</p>}
      {u.state === 'calibrating' && u.progress && <p className="muted small">{w.progress}: {fmt(u.progress.done, 0, lang)}{u.progress.total ? ` / ${fmt(u.progress.total, 0, lang)}` : ''} {tr(u.progress.what, lang)}</p>}
      <div className="card"><div className="card-head"><h3>{w.unitYield}</h3><span className="source">{w.tha} · {tr(m.page.reported_source, lang)}</span></div>
        <YearChart lines={lines} bands={bandsOf(u, w)} unusable={unusable} unit={w.tha} lang={lang} none={w.noYears} />
        {unusable.size > 0 && <div className="muted small"><i className="key key-repx" /> {w.notUsable}: {[...unusable].join(', ')}</div>}
      </div>
      <div className="inputs">
        <div className="card input-card"><div className="card-head"><h3>{w.finalSettings}</h3></div>
          {u.final ? <dl>{m.page.settings.map(s => <Row key={s.id} k={`${tr(s.name, lang) || s.id}${s.name ? ` (${s.id})` : ''}`} v={`${fmt(u.final!.settings[s.id] ?? null, 3, lang)}${s.unit ? ' ' + s.unit : ''}`} note={tr(s.note, lang) || undefined} />)}</dl>
            : <div className="empty">{notYet}</div>}
        </div>
        <div className="card input-card"><div className="card-head"><h3>{w.periods}</h3></div><dl>
          <Row k={w.calYears} v={periodText(u.periods.calibration, w)} />
          <Row k={w.valYears} v={periodText(u.periods.validation, w)} />
        </dl></div>
      </div>
      <div className="card"><div className="card-head"><h3>{w.scores}</h3></div>
        {u.final ? <div className="scroll-x"><table className="tbl">
          <thead><tr><th>{w.part}</th><th title={w.ratioNote}>{w.ratio}</th><th title={w.rNote}>{w.r}</th><th>{w.nYears}</th></tr></thead>
          <tbody>
            <ScoreRows label={w.calYears} p={u.periods.calibration} s={u.final.scores.calibration} w={w} lang={lang} />
            <ScoreRows label={w.valYears} p={u.periods.validation} s={u.final.scores.validation} w={w} lang={lang} />
          </tbody></table>
          <div className="muted small">{w.ratio}: {w.ratioNote}. {w.r}: {w.rNote}.</div></div>
          : <div className="empty">{notYet}</div>}
      </div>
    </>
  )
}

// ---- the project --------------------------------------------------------------------------------------------------
export function ProjectPanel({ m, lives, lang, w, now }: { m: Manifest; lives: Record<string, Live | null>; lang: Lang; w: Words; now: number }) {
  return (
    <>
      <div className="panel-head"><div><div className="eyebrow">{w.projectEye}</div><h2>{tr(m.title, lang)}<small>{w.by} {tr(m.group, lang)}</small></h2></div></div>
      <p className="lead">{tr(m.text, lang)}</p>
      <div className="card input-card"><dl>
        <Row k={w.crop} v={tr(m.page.crop, lang)} />
        <Row k={w.model} v={tr(m.page.model, lang)} />
        <Row k={w.region} v={tr(m.page.region, lang)} />
        <Row k={w.method} v={tr(m.page.method, lang)} />
        <Row k={w.source} v={tr(m.page.reported_source, lang)} />
        <Row k={w.updated} v={when(m.updated_at, lang)} />
      </dl></div>
      <div className="card"><div className="card-head"><h3>{w.runs}</h3></div>
        <ul className="runs">{m.runs.map(r => { const s = stateOf(lives[r.run_id] ?? null, w, lang, now); return (
          <li key={r.run_id}><i className={`sdot ${s.key}`} /><div><b>{tr(r.name, lang)}</b><span className="muted small"> · {w.started} {r.started}</span><div className="small">{s.text}</div></div></li>
        ) })}</ul>
      </div>
    </>
  )
}

// ---- all units: summary + table -----------------------------------------------------------------------------------
type Part = 'calibration' | 'validation'
function summary(units: Unit[], part: Part) {
  const S = units.map(u => u.final?.scores[part]).filter((s): s is Score => !!s && s.ratio !== null)
  const ratios = S.map(s => s.ratio as number), rs = S.map(s => s.r).filter((x): x is number => x !== null)
  return { n: S.length, med: median(ratios), within: ratios.filter(x => x >= 0.9 && x <= 1.1).length, medR: median(rs) }
}
const ORDER: Record<Unit['state'], number> = { calibrating: 0, calibrated: 1, waiting: 2, left_out: 3 }
type SortKey = 'name' | 'state' | 'cells' | 'cr' | 'cR' | 'vr' | 'vR' | `s:${string}`

export function ResultsPanel({ units, cellCount, m, lang, w, onOpen }: {
  units: Unit[]; cellCount: Record<string, number>; m: Manifest; lang: Lang; w: Words; onOpen: (id: string) => void
}) {
  const [q, setQ] = useState('')
  const [all, setAll] = useState(false)
  const [sort, setSort] = useState<{ k: SortKey; up: boolean }>({ k: 'state', up: true })
  const cal = useMemo(() => summary(units, 'calibration'), [units])
  const val = useMemo(() => summary(units, 'validation'), [units])
  const done = units.filter(u => u.state === 'calibrated').length
  const key = (u: Unit, k: SortKey): number | string => {
    const sc = u.final?.scores
    switch (k) {
      case 'name': return tr(u.name, lang)
      case 'state': return ORDER[u.state] ?? 9
      case 'cells': return cellCount[u.id] ?? 0
      case 'cr': return sc?.calibration?.ratio ?? NaN
      case 'cR': return sc?.calibration?.r ?? NaN
      case 'vr': return sc?.validation?.ratio ?? NaN
      case 'vR': return sc?.validation?.r ?? NaN
      default: return u.final?.settings[k.slice(2)] ?? NaN
    }
  }
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase()
    const f = t ? units.filter(u => u.id.toLowerCase().includes(t) || u.name.en.toLowerCase().includes(t) || u.name.zh.includes(q.trim()) || (u.parent?.en ?? '').toLowerCase().includes(t)) : units
    return [...f].sort((a, b) => {
      const x = key(a, sort.k), y = key(b, sort.k)
      const xn = typeof x === 'number' && isNaN(x), yn = typeof y === 'number' && isNaN(y)
      if (xn || yn) return xn && yn ? 0 : xn ? 1 : -1                  // empty values always last
      const c = typeof x === 'string' ? x.localeCompare(String(y)) : (x as number) - (y as number)
      return sort.up ? c : -c
    })
  }, [units, q, sort, lang, cellCount])
  const th = (k: SortKey, label: string, title?: string) => <th className="sortable" title={title} onClick={() => setSort(s => ({ k, up: s.k === k ? !s.up : true }))}>{label}{sort.k === k ? (sort.up ? ' ▲' : ' ▼') : ''}</th>
  const list = all ? shown : shown.slice(0, 25)
  return (
    <>
      <div className="panel-head"><div><div className="eyebrow">{w.resultsEye}</div><h2>{w.resultsTitle}<small>{fmt(done, 0, lang)} {w.of} {fmt(units.length, 0, lang)} {w.calibratedUnits}</small></h2></div>
        <input className="filter" value={q} onChange={e => setQ(e.target.value)} placeholder={w.filter} aria-label={w.filter} /></div>
      <div className="summary">
        {([[w.summaryCal, cal], [w.summaryVal, val]] as const).map(([label, s]) => <div key={label} className="card sum-card">
          <div className="card-head"><h3>{label}</h3></div>
          <div className="sum-grid">
            <div><b>{fmt(s.n, 0, lang)} / {fmt(units.length, 0, lang)}</b><span>{w.scored}</span></div>
            <div><b>{ratioText(s.med, lang)}</b><span>{w.medRatio}</span></div>
            <div><b>{fmt(s.within, 0, lang)}</b><span>{w.within10}</span></div>
            <div><b>{f2(s.medR, lang)}</b><span>{w.medR}</span></div>
          </div></div>)}
      </div>
      <div className="scroll-x"><table className="tbl units-tbl">
        <thead><tr>
          {th('name', w.colName)}{th('state', w.colState)}{th('cells', w.colCells)}
          {m.page.settings.map(s => <th key={s.id} className="sortable" title={tr(s.name, lang)} onClick={() => setSort(o => ({ k: `s:${s.id}`, up: o.k === `s:${s.id}` ? !o.up : true }))}>{s.id}{sort.k === `s:${s.id}` ? (sort.up ? ' ▲' : ' ▼') : ''}</th>)}
          {th('cr', `${w.ratio} · ${w.summaryCal}`, w.ratioNote)}{th('cR', `${w.r} · ${w.summaryCal}`, w.rNote)}
          {th('vr', `${w.ratio} · ${w.summaryVal}`, w.ratioNote)}{th('vR', `${w.r} · ${w.summaryVal}`, w.rNote)}
        </tr></thead>
        <tbody>{list.map(u => { const sc = u.final?.scores; return (
          <tr key={u.id} onClick={() => onOpen(u.id)} className="click">
            <td><b>{tr(u.name, lang)}</b>{u.parent && <div className="muted small">{tr(u.parent, lang)}</div>}</td>
            <td><UnitPill u={u} w={w} /></td>
            <td>{fmt(cellCount[u.id] ?? 0, 0, lang)}</td>
            {m.page.settings.map(s => <td key={s.id}>{fmt(u.final?.settings[s.id] ?? null, 2, lang)}</td>)}
            <td>{f2(sc?.calibration?.ratio, lang)}</td><td>{f2(sc?.calibration?.r, lang)}</td>
            <td>{f2(sc?.validation?.ratio, lang)}</td><td>{f2(sc?.validation?.r, lang)}</td>
          </tr>) })}</tbody>
      </table></div>
      {shown.length > 25 && <button className="more" onClick={() => setAll(!all)}>{all ? w.showLess : `${w.showAll} (${fmt(shown.length, 0, lang)})`}</button>}
    </>
  )
}
