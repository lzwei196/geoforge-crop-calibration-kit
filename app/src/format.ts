import type { Lang, Words } from './i18n'
import type { Live } from './api'
import { tr } from './i18n'

export function fmt(v: unknown, digits = 2, lang: Lang = 'en'): string {
  if (v === null || v === undefined || v === '') return '—'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return '—'
    const x = Math.abs(v) < 0.5 * 10 ** -digits ? 0 : v       // no "-0"
    const a = Math.abs(x)
    const d = Number.isInteger(x) ? 0 : a >= 1000 ? 0 : a >= 100 ? 1 : digits
    return x.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { minimumFractionDigits: 0, maximumFractionDigits: d })
  }
  return String(v)
}
export function when(iso: string | undefined, lang: Lang): string {
  const d = iso ? new Date(iso) : null
  return d && !isNaN(d.getTime()) ? d.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-GB', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
}

// ---- run status: the same rule as the GeoForge Global Runs page ---------------------------------------------------
// "Running now" only when status is running, the process is alive AND the file is less than 3 minutes old.
export type StateKey = 'live' | 'paused' | 'stopped' | 'done' | 'failed' | 'unknown'
export const FRESH_S = 180
export function stateOf(live: Live | null, w: Words, lang: Lang, now = Date.now()): { key: StateKey; text: string } {
  if (!live) return { key: 'unknown', text: w.noStatus }
  if (live.status === 'finished') return { key: 'done', text: w.finished }
  if (live.status === 'failed') return { key: 'failed', text: w.failed }
  const age = (now - new Date(live.exported_at).getTime()) / 1000
  if (!(age <= FRESH_S && age > -60)) return { key: 'unknown', text: w.unknown }     // old file, no time or a wrong clock
  if (live.status === 'running' && live.process_alive) {
    const bits = [w.running]
    if (live.step) bits.push(`${w.step}: ${tr(live.step, lang)}`)
    const p = live.progress
    if (p && Number.isFinite(p.done)) bits.push(`${fmt(p.done, 0, lang)}${p.total ? ' / ' + fmt(p.total, 0, lang) : ''} ${tr(p.what, lang)}`)
    return { key: 'live', text: bits.join(' · ') }
  }
  if (live.status === 'paused') return { key: 'paused', text: w.paused + (live.note ? ` · ${tr(live.note, lang)}` : '') }
  return { key: 'stopped', text: `${w.stopped} · ${w.lastActivity} ${when(live.last_activity, lang)}` }
}
export const RANK: Record<StateKey, number> = { live: 0, paused: 1, stopped: 2, done: 3, failed: 4, unknown: 5 }

// ---- colours (same look as the GeoForge maps) ------------------------------------------------------------------------
const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)]
function ramp(stops: string[], t: number): string {
  if (!Number.isFinite(t)) return '#555'
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1)
  const i = Math.floor(x), f = x - i
  if (i >= stops.length - 1) return stops[stops.length - 1]
  const a = hex(stops[i]), b = hex(stops[i + 1])
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`
}
const VIRIDIS = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
// diverging: red = negative (e.g. moving down), light = about 0, blue = positive
const DIVERGING = ['#d7301f', '#fc8d59', '#fdcc8a', '#f2f2f2', '#9ecae1', '#4292c6', '#2166ac']
export const seqColor = (t: number) => ramp(VIRIDIS, t)
export const divColor = (t: number) => ramp(DIVERGING, t)
export const CLASS_COLORS = ['#38d6c4', '#ffb347', '#c792ea', '#ff6b8b', '#7fd1ff', '#c3e88d', '#f78c6c', '#82aaff', '#e2b93d', '#89ddff']
export const NO_VALUE = 'rgba(139,152,169,.55)'

// colour range: 2nd-98th percentile; diverging ranges are symmetric around their center (0, or 1 for a yield ratio)
export function range(vals: (number | null)[], diverging: boolean, center = 0): [number, number] {
  const v = vals.filter((x): x is number => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b)
  if (!v.length) return diverging ? [center - 1, center + 1] : [0, 1]
  const q = (p: number) => v[Math.min(v.length - 1, Math.max(0, Math.round(p * (v.length - 1))))]
  if (diverging) { const m = Math.max(Math.abs(q(0.02) - center), Math.abs(q(0.98) - center)) || 1; return [center - m, center + m] }
  const lo = q(0.02), hi = q(0.98)
  return hi > lo ? [lo, hi] : [lo - 1, lo + 1]
}

// "Calibration state" colours, by cells.json state: waiting, calibrated, left out, run but no season
export const STATE_COLORS = ['#6b7c93', '#38d6c4', '#ffb347', '#c792ea']

// yield ratio and R as text: a ratio of 0.91 also says "9 % low"
export function ratioText(x: number | null | undefined, lang: Lang): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return '—'
  const p = Math.round((x - 1) * 100)
  const off = p === 0 ? '' : lang === 'zh' ? (p < 0 ? `（偏低 ${-p}%）` : `（偏高 ${p}%）`) : ` (${Math.abs(p)} % ${p < 0 ? 'low' : 'high'})`
  return f2(x, lang) + off
}
export function median(v: number[]): number | null {
  if (!v.length) return null
  const s = [...v].sort((a, b) => a - b), k = Math.floor(s.length / 2)
  return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2
}
// a yield ratio value (coloured around 1): shown with "x % low / high"
export const isRatio = (v: { scale?: string; center?: number }) => v.scale === 'diverging' && v.center === 1
// scores (yield ratio, R) always with two decimals: 1.00, 0.90
export function f2(x: number | null | undefined, lang: Lang): string {
  if (x === null || x === undefined || !Number.isFinite(x)) return '—'
  const v = Math.abs(x) < 0.005 ? 0 : x
  return v.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
