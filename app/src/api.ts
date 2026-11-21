// The files this page reads. They sit in ./data/ next to index.html; docs/DATA_FORMAT.md describes every field.
// tools/csv_to_data.py writes them from your run's tables; tools/check_data.py checks them.
export const DATA = `${import.meta.env.BASE_URL}data/`

export type L = { en: string; zh: string }                       // every text the reader sees comes in both languages
export type ValueDef = {
  id: string; name: L; unit: string; kind: 'num'
  scale?: 'diverging' | 'sequential'; center?: number             // diverging: coloured around center (default 0)
  note?: L
}
export type SettingDef = { id: string; name?: L; unit?: string; note?: L }
export type FeedRun = { run_id: string; name: L; started: string }
export type Manifest = {
  feed_version: 1; project_id: string; example?: boolean; updated_at: string
  data_version: string                                            // the folder v/<data_version>/ that holds this export
  group: L; title: L; text: L; tags: { en: string[]; zh: string[] }; facts?: L[]; map_url?: string
  runs: FeedRun[]
  page: {
    crop: L; model: L; region: L; method: L; reported_source: L; unit_word: L
    grid_deg: number; years: [number, number]
    water: { id: string; name: L }[]
    settings: SettingDef[]
    values: ValueDef[]; default_value: string
    cell_years: { tile_deg: number }
  }
}
// cell states (cells.json "state")
export const WAITING = 0, CALIBRATED = 1, LEFT_OUT = 2, NO_SEASON = 3
export type Cells = {
  id: string[]; water: string[]; lat: number[]; lon: number[]; unit: string[]
  area_ha: (number | null)[]; state: number[]
  values: Record<string, (number | null)[]>
}
export type Score = { n: number; ratio: number | null; r: number | null }
export type UnitState = 'waiting' | 'calibrating' | 'calibrated' | 'left_out'
export type Unit = {
  id: string; name: L; parent?: L; state: UnitState; note?: L
  periods: { calibration: [number, number]; validation: [number, number] | null }
  reported: { years: number[]; yield: (number | null)[]; usable: boolean[] }
  model: { years: number[]; calibrated: (number | null)[]; uncalibrated: (number | null)[] }
  final: null | { settings: Record<string, number | null>; scores: { calibration: Score; validation: Score | null } }
  progress?: { done: number; total?: number; what: L }
}
export type Units = { units: Unit[] }
export type CellYears = { calibrated?: (number | null)[]; uncalibrated?: (number | null)[] }
export type Tile = { years: number[]; cells: Record<string, CellYears> }
export type Live = {
  run_id: string; status: 'running' | 'paused' | 'stopped' | 'finished' | 'failed'; process_alive: boolean
  exported_at: string; last_activity: string; step?: L; note?: L
  progress?: { done: number; total?: number; what: L }
}

// every read has a time limit, so a request that never answers cannot block the page (data: 5 min for big files
// through a slow tunnel; status: 20 s)
// the time limit covers the whole download, body included
export async function getJSON<T>(path: string, ms = 300_000): Promise<T> {
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms)
  try {
    const r = await fetch(DATA + path, { cache: 'no-store', signal: ctl.signal })
    if (!r.ok) throw new Error(`${path}: ${r.status}`)
    return await r.json() as T
  } catch (e) {
    if (ctl.signal.aborted) throw new Error(`${path}: no answer within ${Math.round(ms / 1000)} s`)
    throw e
  } finally { clearTimeout(t) }
}

// the manifest fields the page uses; a manifest without them is never shown
const isL = (x: unknown) => !!x && typeof x === 'object' && typeof (x as L).en === 'string'
export function validManifest(m: unknown): m is Manifest {
  const x = m as Manifest
  if (!x || typeof x !== 'object' || typeof x.data_version !== 'string' || !isL(x.title) || !isL(x.group) || !isL(x.text)) return false
  if (!Array.isArray(x.runs) || !x.runs.every(r => !!r && typeof r.run_id === 'string' && isL(r.name))) return false
  const p = x.page
  return !!p && typeof p === 'object' && typeof p.grid_deg === 'number' && p.grid_deg > 0 && Array.isArray(p.years) && p.years.length === 2
    && Array.isArray(p.water) && p.water.length > 0 && Array.isArray(p.settings) && Array.isArray(p.values)
    && typeof p.default_value === 'string' && !!p.cell_years && typeof p.cell_years.tile_deg === 'number'
    && [p.crop, p.model, p.region, p.method, p.reported_source, p.unit_word].every(isL)
}

// the shapes the page needs before it shows new files (a broken file never replaces good data)
const isList = (x: unknown) => Array.isArray(x)
export function validCells(c: unknown): c is Cells {
  const x = c as Cells
  if (!x || typeof x !== 'object' || !isList(x.id)) return false
  const n = x.id.length
  return [x.water, x.lat, x.lon, x.unit, x.area_ha, x.state].every(a => isList(a) && a.length === n)
    && !!x.values && typeof x.values === 'object' && Object.values(x.values).every(a => isList(a) && a.length === n)
}
export function validUnits(u: unknown): u is Units {
  const x = u as Units
  return !!x && typeof x === 'object' && isList(x.units) && x.units.every(v => !!v && typeof v === 'object' && typeof v.id === 'string'
    && !!v.name && !!v.periods && !!v.reported && !!v.model && isList(v.model.years))
}

// every export lives in its own folder v/<data_version>/, so files of two exports are never mixed
export const vpath = (version: string, file: string) => `v/${encodeURIComponent(version)}/${file}`

// one cell's yearly yields: read the 5° square file once per data version
const tiles = new Map<string, Promise<Tile>>()
export const tileName = (lat: number, lon: number, deg: number) => `${Math.floor(lat / deg) * deg}_${Math.floor(lon / deg) * deg}`
export function loadCellYears(version: string, id: string, water: string, lat: number, lon: number, deg: number): Promise<{ years: number[]; y: CellYears | null }> {
  const t = `${version}/${tileName(lat, lon, deg)}`
  if (!tiles.has(t)) tiles.set(t, getJSON<Tile>(vpath(version, `cell_years/${tileName(lat, lon, deg)}.json`)).catch(e => { tiles.delete(t); throw e }))
  return tiles.get(t)!.then(f => ({ years: f.years, y: f.cells[`${id}|${water}`] ?? null }))
}
export const clearTiles = () => tiles.clear()

// a time is used only with its zone (…Z or …+08:00): without one, a browser would read it as its own local time
// and a real calendar day (a browser would quietly turn 30 February into 2 March)
function zoned(s: string): boolean {
  const m = /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d)(:\d\d(\.\d+)?)?(Z|[+-]\d\d:?\d\d)$/.exec(s)
  if (!m) return false
  const y = +m[1], mo = +m[2], d = +m[3]
  const days = [31, y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
  if (mo < 1 || mo > 12 || d < 1 || d > days[mo - 1] || +m[4] > 23 || +m[5] > 59) return false
  return !isNaN(Date.parse(s.replace(/([+-]\d\d)(\d\d)$/, '$1:$2')))
}

// a live.json is used only when it is well formed and belongs to the run it was read for; otherwise "no status"
const STATUSES = ['running', 'paused', 'stopped', 'finished', 'failed']
export function validLive(x: unknown, runId: string): Live | null {
  const l = x as Live | null
  if (!l || typeof l !== 'object' || l.run_id !== runId || !STATUSES.includes(l.status)) return null
  if (typeof l.process_alive !== 'boolean' || typeof l.exported_at !== 'string' || typeof l.last_activity !== 'string') return null
  if (!zoned(l.exported_at) || !zoned(l.last_activity)) return null
  const norm = (t: string) => t.replace(/([+-]\d\d)(\d\d)$/, '$1:$2')       // +0000 -> +00:00, read the same in every browser
  return { ...l, exported_at: norm(l.exported_at), last_activity: norm(l.last_activity) }
}
