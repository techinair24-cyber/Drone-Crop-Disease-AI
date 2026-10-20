import { useEffect } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, ZoomControl, useMap } from 'react-leaflet'

function FocusMap({ selected }) {
  const map = useMap()
  useEffect(() => {
    if (selected) map.flyTo([selected.latitude, selected.longitude], 14, { duration: 0.7 })
  }, [map, selected])
  return null
}

export default function DetectionMap({ rows, selected, onSelect, center }) {
  return <MapContainer center={center} zoom={4} scrollWheelZoom zoomControl={false}>
    <ZoomControl position="topright" />
    <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
    <FocusMap selected={selected} />
    {rows.map((row) => <CircleMarker
      key={row.id}
      center={[row.latitude, row.longitude]}
      radius={7}
      pathOptions={{ color: row.classification === 'diseased' ? '#ee8e68' : '#a8d95d', fillOpacity: .8 }}
      eventHandlers={{ click: () => onSelect(row) }}
    >
      <Popup><strong>{row.disease_name}</strong><br />{row.crop_name || 'Crop unknown'} · {new Date(row.created_at).toLocaleString()}<br />Score: {Number.isFinite(row.prediction_score) ? `${(row.prediction_score * 100).toFixed(1)}%` : '—'}</Popup>
    </CircleMarker>)}
  </MapContainer>
}
