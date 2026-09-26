import 'leaflet/dist/leaflet.css'
import { useEffect } from 'react'
import { Circle, CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { useI18n } from '../i18n'
import { HEALTH_COLOR } from '../lib/format'

function Fit({ points }) {
  const map = useMap()
  const key = points.map((p) => p.join(',')).join('|')
  useEffect(() => {
    if (!points.length) return
    const lats = points.map((p) => p[0]); const lons = points.map((p) => p[1])
    const fit = () => {
      map.invalidateSize()      // container may have been laid out after the map mounted
      map.fitBounds([[Math.min(...lats) - 0.1, Math.min(...lons) - 0.1],
        [Math.max(...lats) + 0.1, Math.max(...lons) + 0.1]], { maxZoom: 10 })
    }
    fit()
    const t = setTimeout(fit, 250)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return null
}

export default function MapView({ phcs = [], clusters = [], lanes = [], selectedLane, tall, onLaneClick }) {
  const nav = useNavigate()
  const { t } = useI18n()
  const points = phcs.map((p) => [p.lat, p.lon])
  return (
    <div className={`map ${tall ? 'tall' : ''}`}>
      <MapContainer center={[20.5, 80]} zoom={5} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" className="map-tiles" />
        <Fit points={points} />
        {clusters.map((c) => (
          <Circle key={c.id} center={[c.lat, c.lon]} radius={28000}
            pathOptions={{ color: '#c62828', weight: 2, dashArray: '6 6', fillColor: '#c62828', fillOpacity: 0.08 }}>
            <Tooltip sticky>{t('map.cluster', { syndrome: t(`syndrome.${c.syndrome}`), phcs: c.phc_codes.join(', ') })}</Tooltip>
          </Circle>
        ))}
        {lanes.map((s) => {
          const sel = selectedLane === s.id
          return (
            <Polyline key={s.id} positions={[[s.from.lat, s.from.lon], [s.to.lat, s.to.lon]]}
              eventHandlers={{ click: () => onLaneClick?.(s.id) }}
              pathOptions={{ color: sel ? '#c62828' : s.status ? '#1565c0' : '#ef6c00', weight: sel ? 5 : 3, opacity: sel ? 1 : 0.75, dashArray: s.status === 'in_transit' ? '8 6' : undefined }}>
              <Tooltip sticky>{s.from.code} → {s.to.code}: {s.lines.map((l) => `${l.qty} ${l.drug_code}`).join(', ')}</Tooltip>
            </Polyline>
          )
        })}
        {phcs.map((p) => (
          <CircleMarker key={p.id} center={[p.lat, p.lon]} radius={p.anomalies ? 9 : 7}
            eventHandlers={{ click: () => nav(`/phc/${p.id}`) }}
            pathOptions={{ color: '#fff', weight: 1.5, fillColor: HEALTH_COLOR[p.health] || '#999', fillOpacity: 0.95 }}>
            <Tooltip>
              <b>{p.code} · {p.name}</b><br />
              {t('map.score', { score: p.score, n: p.critical_items })}
              {p.anomalies ? <><br />⚠ {t('map.anomaly', { n: p.anomalies })}</> : null}
              {p.reported_today !== undefined && <><br />{p.reported_today ? t('map.reportedToday') : p.stale ? t('report.silent', { n: p.days_since_report }) : t('map.reportDue')}</>}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
