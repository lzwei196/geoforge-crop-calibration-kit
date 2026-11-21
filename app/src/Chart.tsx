import { useState } from 'react'
import type { Lang } from './i18n'
import { fmt } from './format'

// Yearly yield chart: model lines (calibrated solid, uncalibrated dashed), reported yields as dots (grey = not usable),
// calibration and validation years as light bands behind, and a hover readout of every line in the hovered year.
const W = 720, H = 270, PL = 46, PR = 14, PT = 22, PB = 30

export type Line = { id: string; label: string; years: number[]; v: (number | null)[]; kind: 'cal' | 'base' | 'rep' | 'cal2' | 'base2' }
export type Band = { from: number; to: number; label: string; kind: 'cal' | 'val' }

function niceTicks(lo: number, hi: number, n = 5): number[] {
  const span = hi - lo || 1, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => span / s <= n) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10))
  return out
}

export function YearChart({ lines, bands, unusable, unit, lang, none }: {
  lines: Line[]; bands: Band[]; unusable?: Set<number>       // reported years marked not usable (drawn grey)
  unit: string; lang: Lang; none: string
}) {
  const [hy, setHy] = useState<number | null>(null)
  const all = lines.flatMap(l => l.years.map((y, k) => ({ y, v: l.v[k] }))).filter(p => typeof p.v === 'number' && Number.isFinite(p.v)) as { y: number; v: number }[]
  if (all.length < 1) return <div className="empty">{none}</div>
  const yrs = [...lines.flatMap(l => l.years), ...bands.flatMap(b => [b.from, b.to])]
  const y0 = Math.min(...yrs), y1 = Math.max(...yrs)
  const vmax = Math.max(...all.map(p => p.v)) * 1.1 || 1
  const X = (y: number) => PL + ((y - y0 + 0.5) / (y1 - y0 + 1)) * (W - PL - PR)
  const Y = (v: number) => PT + (1 - v / vmax) * (H - PT - PB)
  const step = (W - PL - PR) / (y1 - y0 + 1)
  const path = (l: Line) => {
    let d = '', pen = false
    l.years.forEach((y, k) => { const v = l.v[k]; if (typeof v === 'number' && Number.isFinite(v)) { d += `${pen ? 'L' : 'M'}${X(y).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true } else pen = false })
    return d
  }
  const every = Math.max(1, Math.ceil((y1 - y0 + 1) / 9))
  const move = (e: React.MouseEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * (W - PL - PR) + PL
    setHy(Math.min(y1, Math.max(y0, Math.round(y0 - 0.5 + (x - PL) / step))))
  }
  const valueAt = (l: Line, y: number) => { const k = l.years.indexOf(y); return k < 0 ? null : l.v[k] }
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img">
        {bands.map(b => <g key={b.kind}>
          <rect className={`band-${b.kind}`} x={X(b.from) - step / 2} width={(b.to - b.from + 1) * step} y={PT} height={H - PT - PB} />
          <text className="band-label" x={X(b.from) - step / 2 + 4} y={PT - 7}>{b.label}</text>
        </g>)}
        {niceTicks(0, vmax).map(v => <g key={v}><line className="grid" x1={PL} x2={W - PR} y1={Y(v)} y2={Y(v)} /><text className="tick" x={PL - 6} y={Y(v) + 4} textAnchor="end">{fmt(v, 1, lang)}</text></g>)}
        {Array.from({ length: y1 - y0 + 1 }, (_, k) => y0 + k).filter(y => (y - y0) % every === 0).map(y => <text key={y} className="tick" x={X(y)} y={H - 10} textAnchor="middle">{y}</text>)}
        <text className="axis-label" x={4} y={PT - 7}>{unit}</text>
        {lines.filter(l => l.kind !== 'rep').map(l => <path key={l.id} className={`ln ln-${l.kind}`} d={path(l)} />)}
        {lines.filter(l => l.kind !== 'rep').map(l => l.years.map((y, k) => { const v = l.v[k]; return typeof v === 'number' && Number.isFinite(v) ? <circle key={l.id + y} className={`pt pt-${l.kind}`} cx={X(y)} cy={Y(v)} r={2.2} /> : null }))}
        {lines.filter(l => l.kind === 'rep').map(l => l.years.map((y, k) => { const v = l.v[k]; return typeof v === 'number' && Number.isFinite(v) ? <circle key={l.id + y} className={unusable?.has(y) ? 'rep-x' : 'rep'} cx={X(y)} cy={Y(v)} r={4.2} /> : null }))}
        {hy !== null && <line className="hover-line" x1={X(hy)} x2={X(hy)} y1={PT} y2={H - PB} />}
        <rect x={PL} y={PT} width={W - PL - PR} height={H - PT - PB} fill="transparent" onMouseMove={move} onMouseLeave={() => setHy(null)} onTouchStart={() => setHy(null)} />
      </svg>
      <div className="chart-keys">{lines.map(l => <span key={l.id}><i className={`key key-${l.kind}`} />{l.label}</span>)}</div>
      <div className="chart-read">{hy !== null ? <><b>{hy}</b>{lines.map(l => { const v = valueAt(l, hy); return <span key={l.id}> · {l.label} <b>{v === null || v === undefined ? '—' : fmt(v, 2, lang)}</b>{l.kind === 'rep' && unusable?.has(hy) ? ' *' : ''}</span> })}</> : ' '}</div>
    </div>
  )
}
