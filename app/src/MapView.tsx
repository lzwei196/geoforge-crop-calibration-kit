import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { Cells } from './api'

// Leaflet map + one canvas that draws every cell as a square of grid_deg degrees.
// A canvas (not one shape per cell) keeps hundreds of thousands of cells fast.
// `rows` = the cells.json rows to draw (one water kind); `colors[k]` is the colour of rows[k].
export function MapView({ cells, rows, colors, grid, selected, focus, onPick, onHover }: {
  cells: Cells | null
  rows: number[]
  colors: string[] | null
  grid: number
  selected: number | null                         // a cells.json row
  focus: { bounds: [[number, number], [number, number]]; token: number } | null
  onPick: (row: number | null) => void
  onHover: (h: { row: number; x: number; y: number } | null) => void
}) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const drawRef = useRef<() => void>(() => {})
  const st = useRef({ onPick, onHover }); st.current = { onPick, onHover }
  const lookup = useRef<Map<string, number>>(new Map())          // "i_j" grid square -> row
  const gridRef = useRef(grid); gridRef.current = grid
  const fitted = useRef(false)

  useEffect(() => {
    if (!box.current || mapRef.current) return
    const map = L.map(box.current, { zoomControl: false, minZoom: 2, maxZoom: 12, zoomSnap: 1, wheelPxPerZoomLevel: 90, maxBounds: [[-75, -200], [85, 200]] })
    const esri = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas'
    L.tileLayer(`${esri}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, attribution: 'Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors' }).addTo(map)
    L.tileLayer(`${esri}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 16, pane: 'shadowPane' }).addTo(map)
    L.control.zoom({ position: 'bottomright' }).addTo(map)
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map)
    map.setView([20, 10], 2)                                        // the map then zooms to your cells once they are read
    const c = document.createElement('canvas'); c.className = 'cell-canvas'
    map.getPanes().overlayPane.appendChild(c); canvasRef.current = c
    mapRef.current = map
    let raf = 0
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => drawRef.current()) }
    map.on('move zoom resize viewreset zoomend moveend', schedule)
    const at = (ll: L.LatLng) => {
      const g = gridRef.current
      return lookup.current.get(`${Math.floor(ll.lat / g)}_${Math.floor(ll.lng / g)}`) ?? null
    }
    map.on('click', (e: L.LeafletMouseEvent) => st.current.onPick(at(e.latlng)))
    map.on('mousemove', (e: L.LeafletMouseEvent) => { const r = at(e.latlng); st.current.onHover(r === null ? null : { row: r, x: e.containerPoint.x, y: e.containerPoint.y }) })
    map.on('mouseout', () => st.current.onHover(null))
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(box.current)
    return () => { ro.disconnect(); map.remove(); mapRef.current = null }
  }, [])

  // grid square -> row, for clicks and hover
  useEffect(() => {
    const m = new Map<string, number>()
    if (cells) for (const k of rows) m.set(`${Math.floor(cells.lat[k] / grid)}_${Math.floor(cells.lon[k] / grid)}`, k)
    lookup.current = m
  }, [cells, rows, grid])

  // first time the cells arrive: zoom to them
  useEffect(() => {
    const map = mapRef.current
    if (!map || !cells || fitted.current || !cells.lat.length) return
    let s = 90, n = -90, w = 180, e = -180
    for (let k = 0; k < cells.lat.length; k++) { s = Math.min(s, cells.lat[k]); n = Math.max(n, cells.lat[k]); w = Math.min(w, cells.lon[k]); e = Math.max(e, cells.lon[k]) }
    map.fitBounds([[s - grid, w - grid], [n + grid, e + grid]], { padding: [20, 20], maxZoom: 8 })
    fitted.current = true
  }, [cells, grid])

  drawRef.current = () => {
    const map = mapRef.current, c = canvasRef.current
    if (!map || !c) return
    const size = map.getSize(), dpr = window.devicePixelRatio || 1
    L.DomUtil.setPosition(c, map.containerPointToLayerPoint([0, 0]))
    c.width = size.x * dpr; c.height = size.y * dpr
    c.style.width = `${size.x}px`; c.style.height = `${size.y}px`
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, size.x, size.y)
    if (!cells || !colors) return
    const h = grid / 2, b = map.getBounds().pad(0.05)
    const S = b.getSouth(), N = b.getNorth(), W = b.getWest(), E = b.getEast()
    // squares: both corners rounded to whole pixels, so neighbouring cells touch (no thin gaps) and a cell is
    // never less than 1 px, so small cells stay visible when zoomed out
    const box = (la: number, lo: number) => {
      const a = map.latLngToContainerPoint([la + h, lo - h]), b2 = map.latLngToContainerPoint([la - h, lo + h])
      const x0 = Math.round(a.x), y0 = Math.round(a.y)
      return [x0, y0, Math.max(1, Math.round(b2.x) - x0), Math.max(1, Math.round(b2.y) - y0)] as const
    }
    for (let k = 0; k < rows.length; k++) {
      const r = rows[k], la = cells.lat[r], lo = cells.lon[r]
      if (la < S || la > N || lo < W || lo > E) continue
      const [x, y, bw, bh] = box(la, lo)
      ctx.fillStyle = colors[k]
      ctx.fillRect(x, y, bw, bh)
    }
    if (selected !== null && selected < cells.id.length) {
      const [x, y, bw, bh] = box(cells.lat[selected], cells.lon[selected])
      const pad = 3
      ctx.lineWidth = 2; ctx.strokeStyle = '#ffffff'
      ctx.strokeRect(x - pad, y - pad, bw + 2 * pad, bh + 2 * pad)
    }
  }

  useEffect(() => { drawRef.current() }, [cells, rows, colors, selected, grid])
  useEffect(() => {
    const map = mapRef.current
    if (map && focus) map.flyToBounds(focus.bounds, { padding: [30, 30], maxZoom: 9, duration: 0.8 })
  }, [focus?.token])

  return <div ref={box} className="map" />
}
