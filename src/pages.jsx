import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Activity, AlertCircle, ArrowDownToLine, ArrowRight, Camera, Check, ChevronLeft,
  ChevronRight, CircleHelp, CloudOff, Crosshair, FileImage, ImagePlus, Leaf,
  MapPin, RefreshCw, Search, ShieldAlert, Upload,
} from 'lucide-react'
import { api, exportDetections } from './api.js'

const ActivityChart = lazy(() => import('./ActivityChart.jsx'))
const DetectionMap = lazy(() => import('./DetectionMap.jsx'))
const formatDate = (value) => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
const score = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
const coords = (row) => Number.isFinite(row.latitude) && Number.isFinite(row.longitude)

function PageIntro({ eyebrow = 'DroneCrop AI', title, description, action }) {
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h1 className="page-title">{title}</h1><p className="page-description">{description}</p></div>{action}</div>
}

function ErrorNotice({ error, onRetry }) {
  if (!error) return null
  return <div className="notice warning" role="alert"><AlertCircle size={16} /><span>{error.message || 'Unable to load data.'}</span>{onRetry && <button className="button" onClick={onRetry}><RefreshCw size={13} />Retry</button>}</div>
}

function EmptyState({ title, children, icon: Icon = CloudOff }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={17} /></div><div className="empty-title">{title}</div><p className="empty-copy">{children}</p></div>
}

function useLoad(load, dependencies = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(true)
  const refresh = useCallback(() => {
    setBusy(true)
    setError(null)
    return load().then(setData).catch(setError).finally(() => setBusy(false))
  // Callers provide the request dependencies explicitly.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, dependencies)
  useEffect(() => { refresh() }, [refresh])
  return { data, error, busy, refresh }
}

function StatusIndicator({ label, value }) {
  const available = value === true || value === 'available' || value === 'online'
  return <div className="status-row"><span className="status-label"><span className={`status-dot ${available ? 'online' : ''}`} />{label}</span><span className="status-text">{available ? 'Available' : 'Unavailable'}</span></div>
}

function ActivityRows({ records }) {
  if (!records?.length) return <EmptyState title="No detections yet">Analyzed images will appear here once real model inference is available.</EmptyState>
  return <div className="activity-list">{records.map((row) => <Link key={row.id} to={`/history?id=${encodeURIComponent(row.id)}`} className="activity-item" style={{ textDecoration: 'none' }}>
    {row.image_url ? <img className="thumb" src={api.imageUrl(row.image_url)} alt="" /> : <div className="thumb" />}
    <div className="activity-main"><div className="activity-name">{row.disease_name || 'Inconclusive result'}</div><div className="activity-meta">{row.crop_name || 'Crop unknown'} · {formatDate(row.created_at)}</div></div>
    <span className={`badge ${row.classification === 'diseased' ? 'disease' : 'neutral'}`}>{row.classification || 'inconclusive'}</span>
  </Link>)}</div>
}

export function OverviewPage() {
  const stats = useLoad(() => api.stats(), [])
  const status = useLoad(() => api.status(), [])
  const recent = useLoad(() => api.detections({ page: 1, page_size: 5 }), [])
  const summary = stats.data
  const chart = summary?.activity || []
  const diseaseData = summary?.disease_distribution || []
  return <>
    <PageIntro eyebrow="Field overview" title="Good day, operator" description="A clear view of your crop health intelligence and connected field equipment." action={<Link to="/monitor" className="button primary"><ImagePlus size={14} />Analyze an image</Link>} />
    <ErrorNotice error={stats.error} onRetry={stats.refresh} />
    <div className="grid metric-grid" style={{ marginTop: stats.error ? 14 : 0 }}>
      {[
        ['Images analyzed', summary?.total_images ?? '—', 'Recorded by the backend', FileImage],
        ['Disease detections', summary?.diseased_images ?? '—', 'Model-classified records', ShieldAlert],
        ['Healthy images', summary?.healthy_images ?? '—', 'Model-classified records', Leaf],
        ['With GPS fix', summary?.geolocated_images ?? '—', 'Records with valid coordinates', MapPin],
      ].map(([label, value, note, Icon]) => <div className="card metric-card" key={label}><Icon className="metric-icon" size={18} /><div className="metric-label">{label}</div><div className="metric-value">{stats.busy ? <div className="loading-line" style={{ width: 55 }} /> : value}</div><div className="metric-note">{note}</div></div>)}
    </div>
    <div className="grid overview-middle">
      <div className="card"><div className="card-heading"><div><div className="card-title">Detection activity</div><div className="card-subtitle">Daily analyzed images from backend records</div></div><span className="badge neutral">Last 14 days</span></div>
        {chart.length ? <div className="chart-wrap"><Suspense fallback={<div className="chart-empty">Loading chart…</div>}><ActivityChart data={chart} /></Suspense></div> : <div className="chart-empty">{stats.busy ? 'Loading activity…' : 'No activity records available.'}</div>}
      </div>
      <div className="card"><div className="card-heading"><div><div className="card-title">Field equipment</div><div className="card-subtitle">Live connection status from the backend</div></div><Activity size={15} color="#9bd45b" /></div>
        {status.error && <ErrorNotice error={status.error} onRetry={status.refresh} />}
        <div className="status-list">{[['Camera', status.data?.camera], ['GPS fix', status.data?.gps], ['AI model', status.data?.model], ['Drone telemetry', status.data?.telemetry]].map(([name, value]) => <StatusIndicator key={name} label={name} value={value?.available ?? value?.status} />)}</div>
        <div className="card-subtitle" style={{ lineHeight: 1.6, marginTop: 12 }}>No camera, GPS receiver, or APM telemetry integration is currently configured.</div>
      </div>
    </div>
    <div className="grid overview-bottom">
      <div className="card"><div className="card-heading"><div><div className="card-title">Crop-wise disease distribution</div><div className="card-subtitle">Disease labels from saved model records</div></div></div>
        {diseaseData.length ? <div className="crop-bars">{diseaseData.map((row) => <div key={`${row.crop_name}-${row.disease_name}`}><div className="crop-line"><span>{row.crop_name} · {row.disease_name}</span><span>{row.count}</span></div><div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(3, 100 * row.count / diseaseData[0].count)}%` }} /></div></div>)}</div> : <EmptyState title="Nothing to summarize">Disease distribution will appear after the backend records a real disease-classified image.</EmptyState>}
      </div>
      <div className="card"><div className="card-heading"><div><div className="card-title">Recent detection activity</div><div className="card-subtitle">Latest real records from this system</div></div><Link className="button ghost" to="/history">View history <ArrowRight size={13} /></Link></div>
        <ErrorNotice error={recent.error} onRetry={recent.refresh} />{recent.busy ? <div className="loading-line" /> : <ActivityRows records={recent.data?.items} />}
      </div>
    </div>
  </>
}

export function MonitorPage() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [result, setResult] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('latestAnalysis') || 'null') } catch { return null }
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [gps, setGps] = useState({ latitude: '', longitude: '', fixValid: false, gpsTimestamp: '', capturedAt: '' })
  const deviceStatus = useLoad(() => api.status(), [])
  const navigate = useNavigate()
  const onFile = (event) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    if (!['image/jpeg', 'image/png'].includes(selected.type)) { setError(new Error('Choose a JPG, JPEG, or PNG image.')); event.target.value = ''; setFile(null); setPreview(''); setResult(null); return }
    if (selected.size > 10 * 1024 * 1024) { setError(new Error('Image exceeds the 10 MB upload limit.')); event.target.value = ''; setFile(null); setPreview(''); setResult(null); return }
    setError(null)
    setResult(null)
    if (preview) URL.revokeObjectURL(preview)
    setFile(selected)
    setPreview(URL.createObjectURL(selected))
  }
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const analyze = async () => {
    if (!file) return
    setBusy(true); setError(null)
    try {
      const response = await api.predict(file, gps)
      setResult(response)
      sessionStorage.setItem('latestAnalysis', JSON.stringify(response))
    } catch (cause) { setError(cause) } finally { setBusy(false) }
  }
  const record = result?.detection || result
  return <>
    <PageIntro eyebrow="Image acquisition" title="Live monitoring" description="Camera hardware is not connected. Upload a crop image to request backend analysis." />
    <div className="grid monitor-grid">
      <div className="card">
        <div className="card-heading"><div><div className="card-title">Camera preview</div><div className="card-subtitle">ESP32-CAM integration · pending</div></div><span className="badge neutral"><span className={`status-dot ${deviceStatus.data?.camera?.available ? 'online' : 'offline'}`} style={{ marginRight: 6 }} />{deviceStatus.data?.camera?.available ? 'Available' : 'Offline'}</span></div>
        <div className="camera-view">{preview ? <img className="preview-image" src={preview} alt="Selected crop for analysis" /> : <div className="camera-placeholder"><Camera size={27} /><strong>Live camera unavailable</strong><span>Connect an ESP32-CAM endpoint to enable camera capture.</span></div>}</div>
        <div className="camera-actions">
          <label className="button" htmlFor="crop-upload"><Upload size={14} />Upload image</label>
          <input className="hidden-input" id="crop-upload" type="file" accept="image/jpeg,image/png" onChange={onFile} />
          <button className="button" disabled={!file || busy} onClick={analyze}>{busy ? <RefreshCw size={14} className="spin" /> : <Crosshair size={14} />}{busy ? 'Analyzing…' : 'Analyze image'}</button>
          <button className="button" disabled title="Live monitoring requires an ESP32-CAM backend integration">Start monitoring</button>
          <button className="button" disabled title="Live monitoring requires an ESP32-CAM backend integration">Stop monitoring</button>
          <button className="button" disabled title="Live monitoring requires an ESP32-CAM backend integration">Capture image</button>
        </div>
        {file && <div className="card-subtitle" style={{ marginTop: 11 }}>Selected: {file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB</div>}
        <ErrorNotice error={error} />
      </div>
      <div className="card"><div className="card-heading"><div><div className="card-title">Analysis status</div><div className="card-subtitle">No simulated camera or sensor data</div></div></div>
        <ErrorNotice error={deviceStatus.error} onRetry={deviceStatus.refresh} />
        <div className="status-list"><StatusIndicator label="Camera connection" value={deviceStatus.data?.camera?.available} /><StatusIndicator label="GPS fix" value={deviceStatus.data?.gps?.available} /><StatusIndicator label="Model inference" value={deviceStatus.data?.model?.available} /></div>
        <div className="form-row"><div className="form-label">Optional GPS coordinates</div><div className="form-help">Coordinates are saved only with a valid GPS fix and GPS/capture times within 30 seconds.</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}><input className="field" aria-label="Latitude" placeholder="Latitude" type="number" min="-90" max="90" step="any" value={gps.latitude} onChange={(event) => setGps({ ...gps, latitude: event.target.value })} /><input className="field" aria-label="Longitude" placeholder="Longitude" type="number" min="-180" max="180" step="any" value={gps.longitude} onChange={(event) => setGps({ ...gps, longitude: event.target.value })} /></div>
          <label className="status-label" style={{ marginTop: 12 }}><input type="checkbox" checked={gps.fixValid} onChange={(event) => setGps({ ...gps, fixValid: event.target.checked })} /> GPS fix is valid</label>
          <div style={{ display: 'grid', gap: 7, marginTop: 8 }}><label className="form-help">GPS fix timestamp<input className="field form-input" type="datetime-local" aria-label="GPS fix timestamp" value={gps.gpsTimestamp} onChange={(event) => setGps({ ...gps, gpsTimestamp: event.target.value })} /></label><label className="form-help">Image capture timestamp<input className="field form-input" type="datetime-local" aria-label="Image capture timestamp" value={gps.capturedAt} onChange={(event) => setGps({ ...gps, capturedAt: event.target.value })} /></label></div>
        </div>
        {record && <div className="analysis-result"><div className="card-title" style={{ margin: '15px 0 5px' }}>Latest result</div><div className="result-row"><span>Prediction</span><strong>{record.disease_name || 'Inconclusive'}</strong></div><div className="result-row"><span>Score</span><strong>{score(record.prediction_score)}</strong></div><button className="button" style={{ marginTop: 12 }} onClick={() => navigate('/analysis')}>View analysis <ArrowRight size={13} /></button></div>}
      </div>
    </div>
    <div className="notice warning" style={{ marginTop: 14 }}><CircleHelp size={15} /><span>A model must be installed and loaded by the backend. No prediction is generated when model inference is unavailable.</span></div>
  </>
}

export function AnalysisPage() {
  const [latest] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('latestAnalysis') || 'null') } catch { return null }
  })
  const record = latest?.detection || latest
  return <>
    <PageIntro eyebrow="Model output" title="AI disease analysis" description="Results shown here are returned by backend inference; this interface does not infer disease by itself." action={<Link to="/monitor" className="button"><Upload size={14} />Analyze an image</Link>} />
    {!record ? <div className="card"><EmptyState title="No analysis available">Upload an image and run an inference request to see its model output here.</EmptyState></div> : <>
      {latest.model_available === false && <div className="notice warning" style={{ marginBottom: 14 }}><AlertCircle size={15} /><span>The model is unavailable. No disease prediction was produced. Install a supported local model before analyzing images.</span></div>}
      <div className="grid monitor-grid">
        <div className="card"><div className="card-heading"><div><div className="card-title">Submitted crop image</div><div className="card-subtitle">{formatDate(record.created_at)}</div></div></div>{record.image_url ? <img src={api.imageUrl(record.image_url)} alt="Submitted crop" style={{ width: '100%', maxHeight: 440, objectFit: 'contain', borderRadius: 8, background: '#101713' }} /> : <EmptyState title="Image unavailable">The image file is not available from the backend.</EmptyState>}</div>
        <div className="card"><div className="card-heading"><div><div className="card-title">Prediction result</div><div className="card-subtitle">Model scores are not calibrated probabilities</div></div></div>
          <div className="result-row"><span>Crop</span><strong>{record.crop_name || 'Not identified'}</strong></div><div className="result-row"><span>Label</span><strong>{record.disease_name || 'Inconclusive'}</strong></div><div className="result-row"><span>Classification</span><strong>{record.classification || 'inconclusive'}</strong></div><div className="result-row"><span>Model prediction score</span><strong>{score(record.prediction_score)}</strong></div><div className="result-row"><span>Model</span><strong>{record.model_name || 'Unavailable'}</strong></div><div className="result-row"><span>Version</span><strong>{record.model_version || 'Unavailable'}</strong></div><div className="result-row"><span>Location</span><strong>{coords(record) ? `${record.latitude}, ${record.longitude}` : 'Location unavailable'}</strong></div>
          {record.top_predictions?.length > 0 && <><div className="card-title" style={{ marginTop: 18, marginBottom: 7 }}>Alternative predictions</div>{record.top_predictions.slice(1).map((item) => <div className="result-row" key={item.label}><span>{item.label}</span><strong>{score(item.score)}</strong></div>)}</>}
          <div style={{ display: 'flex', gap: 8, marginTop: 16 }}><Link className="button" to={record.id ? `/history?id=${encodeURIComponent(record.id)}` : '/history'}>View history record</Link><Link className="button ghost" to="/recommendations">Guidance</Link></div>
        </div>
      </div>
    </>}
  </>
}

export function MapPage() {
  const [filters, setFilters] = useState({ crop: '', disease: '', from_date: '', to_date: '' })
  const [selected, setSelected] = useState(null)
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(null)
  const load = useCallback(() => {
    api.allLocations(filters).then((items) => { setError(null); setRows(items) }).catch(setError).finally(() => setBusy(false))
  }, [filters])
  useEffect(() => { load() }, [load])
  const center = selected && coords(selected) ? [selected.latitude, selected.longitude] : rows.length ? [rows[0].latitude, rows[0].longitude] : [20, 0]
  return <>
    <PageIntro eyebrow="Spatial intelligence" title="Disease geolocation" description="Only backend records with validated GPS coordinates are shown on the map." />
    <div className="filters">{[['crop', 'Crop name'], ['disease', 'Disease label']].map(([key, placeholder]) => <input key={key} className="field" placeholder={placeholder} value={filters[key]} onChange={(event) => setFilters({ ...filters, [key]: event.target.value })} />)}<input className="field" aria-label="From date" type="date" value={filters.from_date} onChange={(event) => setFilters({ ...filters, from_date: event.target.value })} /><input className="field" aria-label="To date" type="date" value={filters.to_date} onChange={(event) => setFilters({ ...filters, to_date: event.target.value })} /></div>
    <ErrorNotice error={error} onRetry={load} />
    <div className="map-layout">
      <div className="card" style={{ padding: 10 }}><div className="map-canvas">{rows.length > 0 ? <Suspense fallback={<div className="chart-empty">Loading map…</div>}><DetectionMap rows={rows} selected={selected} onSelect={setSelected} center={center} /></Suspense> : <div className="chart-empty">{busy ? 'Loading locations…' : 'No detections with GPS coordinates.'}</div>}</div></div>
      <div className="card"><div className="card-heading"><div><div className="card-title">Mapped detections</div><div className="card-subtitle">{rows.length} location record{rows.length === 1 ? '' : 's'}</div></div></div>
        {rows.length ? <div className="map-list">{rows.map((row) => <button key={row.id} className="activity-item" onClick={() => setSelected(row)} style={{ width: '100%', textAlign: 'left', background: 'none', border: 0, cursor: 'pointer' }}><MapPin size={15} color={row.classification === 'diseased' ? '#eb9471' : '#a9dc60'} /><div className="activity-main"><div className="activity-name">{row.disease_name}</div><div className="activity-meta">{row.crop_name || 'Unknown crop'} · {formatDate(row.created_at)}</div></div></button>)}</div> : <EmptyState title="No mapped detections">GPS coordinates are unavailable unless they were validly associated with an image.</EmptyState>}
      </div>
    </div>
  </>
}

export function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState({ crop: '', disease: '', from_date: '', to_date: '' })
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(true)
  const [detail, setDetail] = useState(null)
  const [exportError, setExportError] = useState(null)
  const load = useCallback(() => {
    api.detections({ ...filters, search, page, page_size: 10 }).then((result) => { setError(null); setData(result) }).catch(setError).finally(() => setBusy(false))
  }, [filters, search, page])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const id = searchParams.get('id')
    if (id) api.detection(id).then(setDetail).catch(setError)
  }, [searchParams])
  const closeDetail = () => { setDetail(null); setSearchParams({}) }
  const exportCsv = async () => {
    setExportError(null)
    try { await exportDetections({ ...filters, search }) } catch (cause) { setExportError(cause) }
  }
  const items = data?.items || []
  return <>
    <PageIntro eyebrow="Record archive" title="Detection history" description="Search and review saved inference records. Data is served by the configured backend." action={<button className="button" onClick={exportCsv}><ArrowDownToLine size={14} />Export CSV</button>} />
    {exportError && <ErrorNotice error={exportError} />}
    <div className="card">
      <div className="filters">
        <label className="field search-field" style={{ display: 'flex', gap: 8, alignItems: 'center' }}><Search size={14} /><input value={search} onChange={(event) => { setPage(1); setSearch(event.target.value) }} placeholder="Search crop or disease" style={{ background: 'none', border: 0, color: 'inherit', outline: 0, width: '100%' }} /></label>
        <input className="field" placeholder="Crop" value={filters.crop} onChange={(event) => { setPage(1); setFilters({ ...filters, crop: event.target.value }) }} />
        <input className="field" placeholder="Disease" value={filters.disease} onChange={(event) => { setPage(1); setFilters({ ...filters, disease: event.target.value }) }} />
        <input className="field" aria-label="From date" type="date" value={filters.from_date} onChange={(event) => { setPage(1); setFilters({ ...filters, from_date: event.target.value }) }} />
        <input className="field" aria-label="To date" type="date" value={filters.to_date} onChange={(event) => { setPage(1); setFilters({ ...filters, to_date: event.target.value }) }} />
      </div>
      {error && <ErrorNotice error={error} onRetry={load} />}
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Detection</th><th>Crop / disease</th><th>Classification</th><th>Model score</th><th>Date & time</th><th>GPS</th><th /></tr></thead><tbody>
        {!busy && items.map((row) => <tr key={row.id}><td className="table-primary">{row.id.slice(0, 8)}</td><td><div className="table-primary">{row.crop_name || 'Unknown crop'}</div><div className="table-secondary">{row.disease_name || 'Inconclusive'}</div></td><td><span className={`badge ${row.classification === 'diseased' ? 'disease' : 'neutral'}`}>{row.classification || 'inconclusive'}</span></td><td>{score(row.prediction_score)}</td><td>{formatDate(row.created_at)}</td><td>{coords(row) ? `${row.latitude.toFixed(4)}, ${row.longitude.toFixed(4)}` : 'Unavailable'}</td><td><button className="button" onClick={() => setDetail(row)}>Details</button></td></tr>)}
      </tbody></table></div>
      {!busy && !items.length && <EmptyState title="No matching records">Try changing your filters, or analyze an image to create the first real record.</EmptyState>}
      {busy && <div style={{ display: 'grid', gap: 10, padding: 16 }}><div className="loading-line" /><div className="loading-line" /><div className="loading-line" /></div>}
      <div className="pagination"><span>{data ? `${data.total} record${data.total === 1 ? '' : 's'} · page ${data.page} of ${Math.max(1, data.pages)}` : 'Loading records…'}</span><div className="pagination-controls"><button className="button" aria-label="Previous page" disabled={!data || page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}><ChevronLeft size={14} /></button><button className="button" aria-label="Next page" disabled={!data || page >= data.pages} onClick={() => setPage((current) => current + 1)}><ChevronRight size={14} /></button></div></div>
    </div>
    {detail && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) closeDetail() }}><section className="modal" role="dialog" aria-modal="true" aria-label="Detection details"><div className="modal-header"><div><div className="card-title">Detection details</div><div className="card-subtitle">{detail.id}</div></div><button className="button" onClick={closeDetail}>Close</button></div>{detail.image_url && <img src={api.imageUrl(detail.image_url)} alt="Detected crop" style={{ maxWidth: '100%', maxHeight: 250, display: 'block', marginBottom: 14, borderRadius: 8 }} />}{[['Crop', detail.crop_name], ['Disease', detail.disease_name], ['Classification', detail.classification], ['Model score', score(detail.prediction_score)], ['Date', formatDate(detail.created_at)], ['Location', coords(detail) ? `${detail.latitude}, ${detail.longitude}` : 'Location unavailable'], ['Model', detail.model_name], ['Version', detail.model_version]].map(([label, value]) => <div className="result-row" key={label}><span>{label}</span><strong>{value || '—'}</strong></div>)}</section></div>}
  </>
}

export function RecommendationsPage() {
  const [latest] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('latestAnalysis') || 'null') } catch { return null }
  })
  const record = latest?.detection || latest
  return <>
    <PageIntro eyebrow="Responsible guidance" title="Recommendations" description="Visual model output is a screening aid, not a confirmed diagnosis or a substitute for local expertise." />
    <div className="notice warning" style={{ marginBottom: 15 }}><ShieldAlert size={15} /><span>Do not make treatment decisions from an AI prediction alone. Verify serious or unfamiliar symptoms with a qualified agricultural expert.</span></div>
    {record?.disease_name && <div className="card" style={{ marginBottom: 14 }}><div className="card-heading"><div><div className="card-title">Current model label: {record.disease_name}</div><div className="card-subtitle">{record.crop_name || 'Crop not identified'} · {score(record.prediction_score)} prediction score</div></div><span className="badge neutral">Unverified</span></div><p className="page-description" style={{ margin: 0 }}>A maintained, verified crop-specific guidance source is not configured for this label. No disease-specific treatment recommendation is provided.</p></div>}
    <div className="grid recommendation-grid">
      <div className="card rec-card"><h3>Careful next steps</h3><p>Record the affected area and capture a clear image of the full plant and leaf details in consistent lighting. Compare symptoms across more than one plant and revisit the field to observe changes.</p></div>
      <div className="card rec-card"><h3>Verify before action</h3><p>Consult your local agricultural extension service or a qualified crop specialist to confirm a suspected disease. Keep the original image and note the date and field conditions.</p></div>
      <div className="card rec-card"><h3>Prevention and monitoring</h3><p>Follow crop-specific, locally approved integrated pest-management guidance. Maintain routine field scouting and record observations; do not apply treatments based only on an image classifier.</p></div>
      <div className="card rec-card"><h3>Information source status</h3><p>No independently verified, maintained disease reference source is configured in this installation. Specific treatment instructions and chemical dosages are intentionally not shown.</p></div>
    </div>
  </>
}

export function SettingsPage() {
  const [saved, setSaved] = useState(false)
  const [endpoint, setEndpoint] = useState(localStorage.getItem('cameraEndpoint') || '')
  const [refresh, setRefresh] = useState(localStorage.getItem('refreshInterval') || '30000')
  const [mapStyle, setMapStyle] = useState(localStorage.getItem('mapStyle') || 'standard')
  const save = (event) => {
    event.preventDefault()
    localStorage.setItem('cameraEndpoint', endpoint.trim())
    localStorage.setItem('refreshInterval', refresh)
    localStorage.setItem('mapStyle', mapStyle)
    setSaved(true)
    window.setTimeout(() => window.location.reload(), 700)
  }
  return <>
    <PageIntro eyebrow="Workspace configuration" title="Settings" description="Configure browser display preferences and review server-side environment settings." />
    <form onSubmit={save} className="grid settings-layout">
      <div className="card"><div className="card-heading"><div><div className="card-title">Device and display</div><div className="card-subtitle">These preferences are stored in this browser only.</div></div></div>
        <label className="form-row"><div className="form-label">ESP32-CAM endpoint</div><div className="form-help">Saved for future integration planning. The UI does not connect to or proxy an endpoint.</div><input className="field form-input" type="url" placeholder="http://camera.local/stream" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} /></label>
        <label className="form-row"><div className="form-label">Status refresh interval</div><div className="form-help">How often backend health is refreshed.</div><select className="select form-input" value={refresh} onChange={(event) => setRefresh(event.target.value)}><option value="10000">10 seconds</option><option value="30000">30 seconds</option><option value="60000">1 minute</option><option value="300000">5 minutes</option></select></label>
        <label className="form-row"><div className="form-label">Map tiles</div><div className="form-help">Map display provider preference; OpenStreetMap tiles are used in this version.</div><select className="select form-input" value={mapStyle} onChange={(event) => setMapStyle(event.target.value)}><option value="standard">Standard (OpenStreetMap)</option></select></label>
        <div style={{ paddingTop: 14, display: 'flex', alignItems: 'center', gap: 12 }}><button className="button primary" type="submit"><Check size={14} />Save preferences</button>{saved && <span className="card-subtitle">Saved. Applying preferences…</span>}</div>
      </div>
      <div className="card"><div className="card-heading"><div><div className="card-title">Backend connection</div><div className="card-subtitle">API URL is set at build time.</div></div></div>
        <div className="form-row"><div className="form-label">VITE_API_BASE_URL</div><div className="form-help">Set this in your frontend environment (for example, in Vercel project settings), then rebuild. It cannot be safely changed at runtime.</div><code className="field form-input" style={{ display: 'block', overflowWrap: 'anywhere' }}>{api.baseUrl}</code></div>
        <div className="form-row"><div className="form-label">Backend environment</div><div className="form-help">Configure allowed CORS origins, local storage path, model directory, and the model confidence threshold on the backend. Never put server secrets in frontend variables.</div></div>
        <div className="form-row"><div className="form-label">Hardware integration</div><div className="form-help">ESP32-CAM, GPS fix verification, and APM 2.8 telemetry are currently unavailable. This application does not send flight-control or motor-arming commands.</div></div>
      </div>
    </form>
  </>
}
