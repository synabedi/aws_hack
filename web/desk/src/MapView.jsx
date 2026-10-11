import React, { useEffect, useRef } from 'react'
import L from 'leaflet'

export default function MapView({ sites, selected, onSelect, tone }) {
  const el = useRef(null)
  const map = useRef(null)
  const layer = useRef(null)
  useEffect(() => {
    map.current = L.map(el.current, { zoomControl: false, attributionControl: true }).setView([28.63, 77.17], 10)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 18,
    }).addTo(map.current)
    layer.current = L.layerGroup().addTo(map.current)
    return () => map.current.remove()
  }, [])
  useEffect(() => {
    if (!layer.current) return
    layer.current.clearLayers()
    const css = getComputedStyle(document.documentElement)
    sites.forEach((s) => {
      const c = css.getPropertyValue(`--${tone(s)}`).trim()
      L.circleMarker([s.lat, s.lon], {
        radius: s.site_id === selected ? 11 : 7, color: css.getPropertyValue('--ink').trim(),
        weight: s.site_id === selected ? 3 : 1.5, dashArray: s.simulated ? '3 3' : null, fillColor: c, fillOpacity: 0.95,
      }).bindTooltip(`${s.name}${s.simulated ? ' (simulated)' : ''}: ${s.depth == null ? 'no reading yet' : s.depth.toFixed(0) + ' cm'}`)
        .on('click', () => onSelect(s.site_id)).addTo(layer.current)
    })
  }, [sites, selected])
  return <div ref={el} className="map" aria-label="Map of monitored sites" />
}
