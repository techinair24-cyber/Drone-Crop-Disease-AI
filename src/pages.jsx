import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertCircle, ArrowDownToLine, ArrowRight, Camera, Check, ChevronLeft,
  ChevronRight, CloudOff, Crosshair, FileImage, ImagePlus, Leaf,
  MapPin, RefreshCw, Search, ShieldAlert, Upload,
} from 'lucide-react'
import { api, exportDetections } from './api.js'
import { getCurrentLocation, hasValidCoordinates } from './location.js'
import { getLatestDetection, scheduleMonitorRefresh } from './monitoring.js'
import { SUPPORTED_CROPS } from './supportedCrops.js'
import { predictCrop } from './cropPrediction.js'
import { getCropRecommendation, getDetectionHealthStatus } from './recommendationKnowledge.js'

const ActivityChart = lazy(() => import('./ActivityChart.jsx'))
const DetectionMap = lazy(() => import('./DetectionMap.jsx'))
const formatDate = (value) => value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'
const score = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
const displayModelName = (value) => typeof value === 'string' ? value.replace(/\bprototype\b/ig, '').replace(/\s{2,}/g, ' ').trim() : value

function healthGuidance(record) {
  const status = record?.health_status
    || (record?.classification === 'healthy' ? 'Healthy' : record?.classification === 'diseased' ? 'Unhealthy' : null)
  if (status === 'Healthy') return 'Continue routine crop care and monitor plants regularly.'
  if (status === 'Unhealthy') return 'Inspect this plant and nearby leaves. This result does not identify a specific disease or prescribe treatment; consult local agricultural guidance before treating the crop.'
  return null
}

function readStoredAnalysis() {
  try {
    const stored = JSON.parse(sessionStorage.getItem('latestAnalysis') || 'null')
    return stored?.crop_only ? null : stored
  } catch {
    return null
  }
}

function imageValidationError(file) {
  if (!['image/jpeg', 'image/png'].includes(file.type)) return 'Choose a JPG, JPEG, or PNG image.'
  if (file.size > 10 * 1024 * 1024) return 'Image exceeds the 10 MB upload limit.'
  return null
}

function ErrorNotice({ error, onRetry, compact = false }) {
  if (!error) return null
  return <div className={`notice warning${compact ? ' compact-notice' : ''}`} role="alert"><AlertCircle size={16} /><span>{error.message || 'Unable to load data.'}</span>{onRetry && <button className="button" onClick={onRetry}><RefreshCw size={13} />Retry</button>}</div>
}

function EmptyState({ title, icon: Icon = CloudOff }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={17} /></div><div className="empty-title">{title}</div></div>
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

function StatusIndicator({ label, value, loading = false }) {
  const available = value === true || value === 'available' || value === 'online'
  return <div className="status-row"><span className="status-label"><span className={`status-dot ${available ? 'online' : loading ? '' : 'offline'}`} />{label}</span><span className="status-text">{loading ? 'Checking' : available ? 'Available' : 'Unavailable'}</span></div>
}

function getOverviewStatus(value) {
  if (!value || typeof value !== 'object') return null
  if (value.status === 'not_configured') return 'Not configured'
  if (value.status === 'error') return 'Error'
  if (typeof value.available === 'boolean') return value.available ? 'Available' : 'Unavailable'
  if (value.status === 'available' || value.status === 'online') return 'Available'
  if (value.status === 'unavailable' || value.status === 'offline') return 'Unavailable'
  return null
}

function OverviewStatusRow({ label, status }) {
  return <div className="overview-status-row">
    <span>{label}</span>
    <span className="overview-status-value">
      <span className={`overview-status-dot${status === 'Available' ? ' available' : ''}`} />
      {status}
    </span>
  </div>
}

function ActivityRows({ records }) {
  if (!records?.length) return <EmptyState title="No detections yet" />
  return <div className="activity-list">{records.map((row) => <Link key={row.id} to={`/history?id=${encodeURIComponent(row.id)}`} className="activity-item" style={{ textDecoration: 'none' }}>
    {row.image_url ? <img className="thumb" src={api.imageUrl(row.image_url)} alt="" /> : <div className="thumb" />}
    <div className="activity-main"><div className="activity-name">{row.health_status || row.disease_name || 'Inconclusive result'}</div><div className="activity-meta">{row.crop_name || 'Crop unknown'} · {formatDate(row.created_at)}</div></div>
    <span className={`badge ${row.classification === 'diseased' ? 'disease' : 'neutral'}`}>{row.health_status || row.classification || 'inconclusive'}</span>
  </Link>)}</div>
}

export function OverviewPage() {
  const stats = useLoad(() => api.stats(), [])
  const status = useLoad(() => api.status(), [])
  const recent = useLoad(() => api.detections({ page: 1, page_size: 5 }), [])
  const summary = stats.data
  const chart = summary?.activity || []
  const deviceStatuses = [
    ['Camera', getOverviewStatus(status.data?.camera)],
    ['AI Model', getOverviewStatus(status.data?.model)],
    ['Telemetry', getOverviewStatus(status.data?.telemetry)],
  ].filter(([, value]) => value !== null)
  return <>
    <div className="overview-heading"><h1 className="page-title">Overview</h1></div>
    <div className="grid metric-grid overview-metrics">
      {[
        ['Images Analyzed', summary?.total_images ?? '—', FileImage],
        ['Disease Detections', summary?.diseased_images ?? '—', ShieldAlert],
        ['Healthy Images', summary?.healthy_images ?? '—', Leaf],
        ['Inconclusive Images', summary?.inconclusive_images ?? '—', AlertCircle],
      ].map(([label, value, Icon]) => <div className="card metric-card" key={label}><Icon className="metric-icon" size={18} /><div className="metric-label">{label}</div><div className="metric-value">{stats.busy ? <div className="loading-line" style={{ width: 55 }} /> : value}</div></div>)}
    </div>
    <div className="grid overview-panels">
      <div className="card"><div className="card-heading"><div className="card-title">Detection Activity</div></div>
        {stats.error ? <ErrorNotice error={stats.error} onRetry={stats.refresh} compact /> : chart.length ? <div className="chart-wrap"><Suspense fallback={<div className="chart-empty">Loading…</div>}><ActivityChart data={chart} /></Suspense></div> : <div className="overview-empty">No activity</div>}
      </div>
      <div className="card"><div className="card-heading"><div className="card-title">Drone Status</div></div>
        {status.error ? <ErrorNotice error={status.error} onRetry={status.refresh} compact /> : deviceStatuses.length ? <div className="overview-status-list">{deviceStatuses.map(([label, value]) => <OverviewStatusRow key={label} label={label} status={value} />)}</div> : <div className="overview-empty">{status.busy ? 'Loading…' : 'Status unavailable'}</div>}
      </div>
    </div>
    <div className="card overview-recent"><div className="card-heading"><div className="card-title">Recent Detections</div><Link className="button ghost" to="/history">View history <ArrowRight size={13} /></Link></div>
        {recent.error ? <ErrorNotice error={recent.error} onRetry={recent.refresh} compact /> : recent.busy ? <div className="loading-line" /> : <ActivityRows records={recent.data?.items} />}
      </div>
  </>
}

export function MonitorPage() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [selectedCrop, setSelectedCrop] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [locationMessage, setLocationMessage] = useState('')
  const latest = useLoad(() => getLatestDetection(api.detections), [])
  const [failedRemoteImageUrl, setFailedRemoteImageUrl] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    const timer = scheduleMonitorRefresh(latest.refresh)
    return () => window.clearInterval(timer)
  }, [latest.refresh])
  const latestRecord = result || latest.data
  const record = latestRecord?.crop_only ? null : latestRecord
  const remoteImageUrl = record?.image_url ? api.imageUrl(record.image_url) : ''
  const onFile = (event) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    const validationError = imageValidationError(selected)
    if (validationError) { setError(new Error(validationError)); event.target.value = ''; setFile(null); setPreview(''); setResult(null); return }
    setError(null)
    setLocationMessage('')
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
      const location = await getCurrentLocation()
      setLocationMessage(location.message)
      const response = await predictCrop(
        api,
        file,
        selectedCrop,
        location.coordinates,
        'live_monitoring',
      )
      setResult(response)
      sessionStorage.setItem('latestAnalysis', JSON.stringify(response))
    } catch (cause) { setError(cause) } finally { setBusy(false) }
  }
  const cameraAvailable = Boolean(remoteImageUrl) && remoteImageUrl !== failedRemoteImageUrl
  const cameraStatus = cameraAvailable ? 'Available' : latest.busy && !record ? null : 'Unavailable'
  const cameraPlaceholder = cameraStatus === 'Available'
    ? 'Feed unavailable'
    : cameraStatus === 'Unavailable'
      ? 'Camera unavailable'
      : latest.busy
        ? 'Checking camera'
        : 'Camera status unavailable'
  return <>
    <div className="monitor-page">
      <div className="monitor-page-heading"><h1 className="page-title">Live monitoring</h1></div>
      <div className="grid live-monitor-grid">
        <div className="card live-monitor-preview-card">
          <div className="card-heading">
            <div className="card-title">Camera Preview</div>
            {cameraStatus && <span className={`badge ${cameraStatus === 'Available' ? '' : 'neutral'}`}>{cameraStatus}</span>}
          </div>
          <div className="camera-view live-monitor-camera-view">
            {preview || cameraAvailable
              ? <img className="preview-image" src={preview || remoteImageUrl} alt={preview ? 'Selected crop for analysis' : 'Latest camera image'} onError={() => { if (!preview) setFailedRemoteImageUrl(remoteImageUrl) }} />
              : <div className="camera-placeholder"><Camera size={27} /><strong>{cameraPlaceholder}</strong></div>}
          </div>
          <div className="camera-actions live-monitor-actions">
            <input className="hidden-input" id="crop-upload" type="file" accept="image/jpeg,image/png" onChange={onFile} />
            <label className="button" htmlFor="crop-upload"><Upload size={14} />Upload image</label>
            <select className="select" aria-label="Crop type" value={selectedCrop} onChange={(event) => setSelectedCrop(event.target.value)} disabled={busy}>
              <option value="">Automatic Crop Detection</option>
              {SUPPORTED_CROPS.map((crop) => <option key={crop} value={crop}>{crop}</option>)}
            </select>
            <button className="button primary" disabled={!file || busy} onClick={analyze}>{busy ? <RefreshCw size={14} className="spin" /> : <Crosshair size={14} />}{busy ? 'Analyzing…' : 'Analyze image'}</button>
          </div>
          {file && <div className="card-subtitle live-monitor-file">{file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB</div>}
          {locationMessage && <div className="analysis-location-message" role="status">{locationMessage}</div>}
          <ErrorNotice error={error} />
        </div>
        <div className="live-monitor-side">
          <div className="card">
            <div className="card-heading"><div className="card-title">Drone Status</div></div>
            <ErrorNotice error={latest.error} onRetry={latest.refresh} compact />
            {!latest.error && <div className="status-list">
              <StatusIndicator label="Camera" value={cameraAvailable} loading={latest.busy && !record} />
            </div>}
          </div>
          {record && <div className="card analysis-result live-monitor-result">
            <div className="card-heading"><div className="card-title">Latest Result</div></div>
            <div className="result-row"><span>Identified crop</span><strong>{record.crop_name || 'Unknown'}</strong></div>
            <div className="result-row"><span>Crop confidence</span><strong>{score(record.crop_confidence)}</strong></div>
            <div className="result-row"><span>Health status</span><strong><span className={`badge ${record.classification === 'diseased' ? 'disease' : 'neutral'}`}>{record.health_status || (record.classification === 'healthy' ? 'Healthy' : record.classification === 'diseased' ? 'Unhealthy' : 'Unknown')}</span></strong></div>
            <div className="result-row"><span>Health confidence</span><strong>{score(record.health_confidence ?? record.prediction_score)}</strong></div>
            {record.message && <p role="status">{record.message}</p>}
            <div className="recommendation-solution-actions">
              <button className="button" onClick={() => navigate('/analysis')}>View analysis <ArrowRight size={13} /></button>
              <Link className="button ghost" to={record.id ? `/recommendations?detection=${encodeURIComponent(record.id)}` : '/recommendations'}>Crop guidance</Link>
            </div>
          </div>}
        </div>
      </div>
    </div>
  </>
}

export function AnalysisPage() {
  const [latest, setLatest] = useState(readStoredAnalysis)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [selectedCrop, setSelectedCrop] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [locationMessage, setLocationMessage] = useState('')
  const record = latest?.detection || latest
  const onFile = (event) => {
    const selected = event.target.files?.[0]
    if (!selected) return
    const validationError = imageValidationError(selected)
    if (validationError) { setError(new Error(validationError)); event.target.value = ''; setFile(null); setPreview(''); setLatest(null); return }
    setError(null)
    setLocationMessage('')
    setLatest(null)
    if (preview) URL.revokeObjectURL(preview)
    setFile(selected)
    setPreview(URL.createObjectURL(selected))
  }
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  const analyze = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const location = await getCurrentLocation()
      setLocationMessage(location.message)
      const response = await predictCrop(
        api,
        file,
        selectedCrop,
        location.coordinates,
        'analysis',
      )
      setLatest(response)
      sessionStorage.setItem('latestAnalysis', JSON.stringify(response))
    } catch (cause) { setError(cause) } finally { setBusy(false) }
  }
  const recommendations = record?.treatment_recommendations ?? record?.recommendations
  const recommendationValues = Array.isArray(recommendations)
    ? recommendations
    : typeof recommendations === 'string' && recommendations.trim()
      ? [recommendations]
      : []
  const recommendationItems = recommendationValues
    .map((item) => typeof item === 'string' ? item : item?.recommendation || item?.text)
    .filter((item) => typeof item === 'string' && item.trim())
  const guidance = healthGuidance(record)
  return <>
    <div className="analysis-page">
      <div className="analysis-page-heading"><h1 className="page-title">AI Analysis</h1></div>
      <div className="grid analysis-page-grid">
        <section className="card analysis-upload-card" aria-labelledby="analysis-upload-heading">
          <div className="card-heading"><div className="card-title" id="analysis-upload-heading">Crop image</div></div>
          <div className="analysis-image-preview">
            {preview
              ? <img src={preview} alt="Selected crop leaf" />
              : record?.image_url
                ? <img src={api.imageUrl(record.image_url)} alt="Previously analyzed crop leaf" />
                : <div className="analysis-preview-empty"><ImagePlus size={22} /><span>No image selected</span></div>}
          </div>
          <div className="camera-actions analysis-actions">
            <input className="hidden-input" id="analysis-upload" type="file" accept="image/jpeg,image/png" onChange={onFile} />
            <label className="button" htmlFor="analysis-upload"><Upload size={14} />Upload image</label>
            <select className="select" aria-label="Crop type" value={selectedCrop} onChange={(event) => setSelectedCrop(event.target.value)} disabled={busy}>
              <option value="">Automatic Crop Detection</option>
              {SUPPORTED_CROPS.map((crop) => <option key={crop} value={crop}>{crop}</option>)}
            </select>
            <button className="button primary" disabled={!file || busy} onClick={analyze}>
              {busy ? <RefreshCw size={14} className="spin" /> : <Crosshair size={14} />}
              {busy ? 'Analyzing…' : 'Analyze image'}
            </button>
          </div>
          {file && <div className="card-subtitle analysis-file-name">{file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB</div>}
          {locationMessage && <div className="analysis-location-message" role="status">{locationMessage}</div>}
          {error && <div className="analysis-error" role="alert">{error.message || 'Analysis request failed.'}</div>}
        </section>
        <section className="card analysis-result-card" aria-labelledby="analysis-result-heading">
          <div className="card-heading"><div className="card-title" id="analysis-result-heading">Analysis result</div></div>
          {busy
            ? <div className="analysis-result-empty" role="status">Analyzing image…</div>
            : !record
              ? <div className="analysis-result-empty">{error ? 'Analysis unavailable' : 'No result yet'}</div>
              : <>
                <div className="analysis-prediction">
                  <span>Identified crop</span>
                  <strong>{record.crop_name || 'Unknown'}</strong>
                </div>
                {Number.isFinite(record.crop_confidence) && <div className="analysis-confidence">
                  <span>Crop confidence</span>
                  <strong>{score(record.crop_confidence)}</strong>
                </div>}
                <div className="analysis-prediction">
                  <span>Health status</span>
                  <strong><span className={`badge ${record.classification === 'diseased' ? 'disease' : 'neutral'}`}>{record.health_status || (record.classification === 'healthy' ? 'Healthy' : record.classification === 'diseased' ? 'Unhealthy' : 'Unknown')}</span></strong>
                </div>
                {Number.isFinite(record.health_confidence ?? record.prediction_score) && <div className="analysis-confidence">
                  <span>Health confidence</span>
                  <strong>{score(record.health_confidence ?? record.prediction_score)}</strong>
                </div>}
                {record.message && <p role="status">{record.message}</p>}
                {record.top_predictions?.length > 1 && <div className="analysis-alternatives">
                  {record.top_predictions.map((item) => <div className="analysis-alternative" key={item.label}>
                    <span>{item.label}</span><strong>{score(item.score)}</strong>
                  </div>)}
                </div>}
                {(recommendationItems.length > 0 || guidance) && <div className="analysis-recommendations">
                  <div className="card-title">Recommendations</div>
                  {recommendationItems.map((item, index) => <p key={`${index}-${item}`}>{item}</p>)}
                  {guidance && <p>{guidance}</p>}
                </div>}
                <div className="analysis-result-links">
                  <Link className="button" to={record.id ? `/history?id=${encodeURIComponent(record.id)}` : '/history'}>View history</Link>
                  <Link className="button ghost" to={record.id ? `/recommendations?detection=${encodeURIComponent(record.id)}` : '/recommendations'}>Crop guidance</Link>
                </div>
              </>}
        </section>
      </div>
    </div>
  </>
}

export function MapPage() {
  const [filters, setFilters] = useState({ disease: '', from_date: '', to_date: '' })
  const [selected, setSelected] = useState(null)
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState(null)
  const requestId = useRef(0)
  const load = useCallback(() => {
    const currentRequest = ++requestId.current
    api.allLocations(filters)
      .then((items) => {
        if (currentRequest === requestId.current) {
          setError(null)
          setRows(items)
        }
      })
      .catch((cause) => {
        if (currentRequest === requestId.current) setError(cause)
      })
      .finally(() => {
        if (currentRequest === requestId.current) setBusy(false)
      })
  }, [filters])
  useEffect(() => {
    load()
    return () => { requestId.current += 1 }
  }, [load])
  const refresh = () => {
    setBusy(true)
    setError(null)
    load()
  }
  const updateFilter = (key, value) => {
    setSelected(null)
    setBusy(true)
    setFilters((current) => ({ ...current, [key]: value }))
  }
  const mapRows = rows.filter(hasValidCoordinates)
  const center = selected && mapRows.some((row) => row.id === selected.id)
    ? [selected.latitude, selected.longitude]
    : mapRows.length
      ? [mapRows[0].latitude, mapRows[0].longitude]
      : [20, 0]
  return <>
    <div className="disease-map-page">
      <div className="disease-map-heading"><h1 className="page-title">Disease Map</h1></div>
      <div className="filters disease-map-filters">
        <input className="field" aria-label="Filter by disease class" placeholder="Disease class" value={filters.disease} onChange={(event) => updateFilter('disease', event.target.value)} />
        <label className="disease-map-date">From<input className="field" aria-label="From date" type="date" value={filters.from_date} onChange={(event) => updateFilter('from_date', event.target.value)} /></label>
        <label className="disease-map-date">To<input className="field" aria-label="To date" type="date" value={filters.to_date} onChange={(event) => updateFilter('to_date', event.target.value)} /></label>
      </div>
      <ErrorNotice error={error} onRetry={refresh} compact />
      <div className="grid map-layout disease-map-layout">
        <div className="card disease-map-card"><div className="map-canvas disease-map-canvas">
          {error ? <div className="disease-map-empty">Map unavailable</div> : busy ? <div className="disease-map-empty">Loading map…</div> : mapRows.length
            ? <Suspense fallback={<div className="disease-map-empty">Loading map…</div>}><DetectionMap rows={mapRows} selected={selected} onSelect={setSelected} center={center} /></Suspense>
            : <div className="disease-map-empty">No detections with location</div>}
        </div></div>
        <div className="card disease-map-list-card">
          <div className="card-heading"><div className="card-title">Mapped detections</div><span className="badge neutral">{busy ? '…' : mapRows.length}</span></div>
          {!busy && !error && mapRows.length ? <div className="map-list">{mapRows.map((row) => <button key={row.id} className={`activity-item disease-map-row${selected?.id === row.id ? ' selected' : ''}`} onClick={() => setSelected(row)}>
            <MapPin size={15} aria-hidden="true" />
            <div className="activity-main"><div className="activity-name">{row.disease_name}</div><div className="activity-meta">{formatDate(row.created_at)}</div></div>
          </button>)}</div> : <div className="disease-map-empty disease-map-list-empty">{busy ? 'Loading detections…' : error ? 'Detections unavailable' : 'No detections with location'}</div>}
        </div>
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
  const requestId = useRef(0)
  const load = useCallback(() => {
    const currentRequest = ++requestId.current
    api.detections({ ...filters, search, page, page_size: 10 })
      .then((result) => {
        if (currentRequest === requestId.current) setData(result)
      })
      .catch((cause) => {
        if (currentRequest === requestId.current) setError(cause)
      })
      .finally(() => {
        if (currentRequest === requestId.current) setBusy(false)
      })
  }, [filters, search, page])
  useEffect(() => {
    load()
    return () => { requestId.current += 1 }
  }, [load])
  const updateFilter = (key, value) => {
    setBusy(true)
    setError(null)
    setPage(1)
    setFilters((current) => ({ ...current, [key]: value }))
  }
  const retry = () => {
    setBusy(true)
    setError(null)
    load()
  }
  useEffect(() => {
    const id = searchParams.get('id')
    if (id) api.detection(id).then(setDetail).catch(setError)
  }, [searchParams])
  const closeDetail = () => { setDetail(null); setSearchParams({}) }
  const openDetail = (row) => {
    setDetail(row)
    setSearchParams({ id: row.id })
  }
  const exportCsv = async () => {
    setExportError(null)
    try { await exportDetections({ ...filters, search }) } catch (cause) { setExportError(cause) }
  }
  const items = data?.items || []
  return <>
    <div className="history-page">
      <div className="history-heading">
        <h1 className="page-title">Detection History</h1>
        <button className="button" onClick={exportCsv}><ArrowDownToLine size={14} />Export CSV</button>
      </div>
      {exportError && <div className="history-message" role="alert">{exportError.message || 'Export failed.'}</div>}
      <section className="card history-card" aria-label="Detection records">
        <div className="filters history-filters">
          <label className="field search-field history-search"><Search size={14} aria-hidden="true" /><input aria-label="Search crop or disease" value={search} onChange={(event) => { setBusy(true); setError(null); setPage(1); setSearch(event.target.value) }} placeholder="Search crop or disease" /></label>
          <input className="field" aria-label="Filter by crop" placeholder="Crop" value={filters.crop} onChange={(event) => updateFilter('crop', event.target.value)} />
          <input className="field" aria-label="Filter by disease" placeholder="Disease" value={filters.disease} onChange={(event) => updateFilter('disease', event.target.value)} />
          <label className="history-date">From<input className="field" aria-label="From date" type="date" value={filters.from_date} onChange={(event) => updateFilter('from_date', event.target.value)} /></label>
          <label className="history-date">To<input className="field" aria-label="To date" type="date" value={filters.to_date} onChange={(event) => updateFilter('to_date', event.target.value)} /></label>
        </div>
        {error && <div className="history-message" role="alert"><span>{error.message || 'Unable to load records.'}</span><button className="button" onClick={retry}>Retry</button></div>}
        {!busy && !error && items.length > 0 && <>
          <div className="history-list-head" aria-hidden="true"><span>Detection</span><span>Confidence</span><span>Date & time</span><span /></div>
          <div className="history-record-list">
            {items.map((row) => (
              <article className="history-record" key={row.id}>
                <div className="history-detection">
                  {row.image_url
                    ? <img className="history-thumb" src={api.imageUrl(row.image_url)} alt="" />
                    : <div className="history-thumb history-thumb-empty" aria-hidden="true" />}
                  <div className="history-record-main">
                    <div className="history-disease">{row.disease_name}</div>
                    <div className="history-meta">{row.crop_name || 'Unknown crop'} · {row.health_status || row.classification}</div>
                  </div>
                </div>
                <div className="history-field"><span className="history-mobile-label">Confidence</span>{score(row.prediction_score)}</div>
                <div className="history-field"><span className="history-mobile-label">Date & time</span>{formatDate(row.created_at)}</div>
                <div className="history-actions"><button className="button" onClick={() => openDetail(row)}>Details</button></div>
              </article>
            ))}
          </div>
        </>}
        {!busy && !error && !items.length && <div className="history-empty">No matching records</div>}
        {busy && <div className="history-loading" role="status">Loading records…</div>}
        <div className="pagination history-pagination">
          <span>{data ? `${data.total} record${data.total === 1 ? '' : 's'} · page ${data.page} of ${Math.max(1, data.pages)}` : ''}</span>
          <div className="pagination-controls">
            <button className="button" aria-label="Previous page" disabled={busy || !data || page <= 1} onClick={() => { setBusy(true); setError(null); setPage((current) => Math.max(1, current - 1)) }}><ChevronLeft size={14} /></button>
            <button className="button" aria-label="Next page" disabled={busy || !data || page >= data.pages} onClick={() => { setBusy(true); setError(null); setPage((current) => current + 1) }}><ChevronRight size={14} /></button>
          </div>
        </div>
      </section>
      {detail && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) closeDetail() }}><section className="modal" role="dialog" aria-modal="true" aria-label="Detection details"><div className="modal-header"><div><div className="card-title">Detection details</div></div><button className="button" onClick={closeDetail}>Close</button></div>{detail.image_url && <img src={api.imageUrl(detail.image_url)} alt="Detected crop" style={{ maxWidth: '100%', maxHeight: 250, display: 'block', marginBottom: 14, borderRadius: 8 }} />}{[['Crop', detail.crop_name], ['Crop confidence', score(detail.crop_confidence)], ['Health status', detail.health_status || detail.disease_name], ['Health confidence', score(detail.health_confidence ?? detail.prediction_score)], ['Date', formatDate(detail.created_at)], ['Model name', displayModelName(detail.model_name)]].map(([label, value]) => <div className="result-row" key={label}><span>{label}</span><strong>{value || '—'}</strong></div>)}</section></div>}
    </div>
  </>
}

export function RecommendationsPage() {
  const detections = useLoad(() => api.allRecommendations(), [])
  const [cropFilter, setCropFilter] = useState('')
  const [reviewBusyId, setReviewBusyId] = useState('')
  const [reviewError, setReviewError] = useState(null)
  const [geminiBusyId, setGeminiBusyId] = useState('')
  const [geminiError, setGeminiError] = useState(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('detection')
  const records = (detections.data?.items || []).filter((record) => (
    record.id
    && record.image_url
    && ['analysis', 'live_monitoring'].includes(record.source)
    && SUPPORTED_CROPS.includes(record.crop_name)
    && getDetectionHealthStatus(record) === 'Unhealthy'
  ))
  const summary = detections.data?.summary
  const cropCounts = SUPPORTED_CROPS.map((crop) => ({
    crop,
    count: summary?.crop_counts?.[crop] || 0,
  }))
  const filteredRecords = records.filter((record) => !cropFilter || record.crop_name === cropFilter)
  const selected = filteredRecords.find((record) => record.id === selectedId)
    || records.find((record) => record.id === selectedId)
  const closeSolution = () => setSearchParams({})
  const showSolution = (record) => setSearchParams({ detection: record.id })
  const markReviewed = async (record) => {
    setReviewError(null)
    setReviewBusyId(record.id)
    try {
      await api.markRecommendationReviewed(record.id)
      await detections.refresh()
    } catch (cause) {
      setReviewError(cause)
    } finally {
      setReviewBusyId('')
    }
  }
  const recommendationsFor = (record) => getCropRecommendation(record.crop_name)
  const retryGemini = async (record) => {
    setGeminiError(null)
    setGeminiBusyId(record.id)
    try {
      await api.retryGeminiAnalysis(record.id)
      await detections.refresh()
    } catch (cause) {
      setGeminiError(cause)
    } finally {
      setGeminiBusyId('')
    }
  }

  return <>
    <div className="recommendations-page">
      <div className="recommendations-heading">
        <div>
          <h1 className="page-title">Crop Treatment &amp; Solution Centre</h1>
          <div className="recommendations-context">Crop-specific guidance linked to saved AI detections</div>
        </div>
        <button className="button" onClick={detections.refresh} disabled={detections.busy}><RefreshCw size={14} className={detections.busy ? 'spin' : ''} />Refresh</button>
      </div>
      {detections.error && <ErrorNotice error={detections.error} onRetry={detections.refresh} />}
      {reviewError && <ErrorNotice error={reviewError} />}
      {geminiError && <ErrorNotice error={geminiError} />}
      {!detections.error && <div className="recommendations-summary">
        <article className="card recommendations-metric"><span>Total unhealthy detections</span><strong>{detections.busy && !detections.data ? '…' : summary?.total_unhealthy ?? 0}</strong></article>
        <article className="card recommendations-metric"><span>Pending recommendations</span><strong>{detections.busy && !detections.data ? '…' : summary?.pending ?? 0}</strong></article>
        <article className="card recommendations-metric"><span>Reviewed recommendations</span><strong>{detections.busy && !detections.data ? '…' : summary?.reviewed ?? 0}</strong></article>
      </div>}
      {!detections.error && <section className="card recommendations-crop-summary" aria-label="Unhealthy detections by crop">
        <div className="card-heading"><div className="card-title">Crop-wise unhealthy detections</div></div>
        <div className="recommendations-crop-counts">
          {cropCounts.map(({ crop, count }) => <div className="recommendations-crop-count" key={crop}><span>{crop}</span><strong>{count}</strong></div>)}
        </div>
      </section>}
      <section className="card recommendations-records-card" aria-label="Detection recommendations">
        <div className="recommendations-filters">
          <label className="recommendations-filter">Crop
            <select className="select" aria-label="Filter recommendations by crop" value={cropFilter} onChange={(event) => setCropFilter(event.target.value)}>
              <option value="">All crops</option>
              {SUPPORTED_CROPS.map((crop) => <option key={crop} value={crop}>{crop}</option>)}
            </select>
          </label>
          <span className="recommendations-result-count">{filteredRecords.length} detection{filteredRecords.length === 1 ? '' : 's'}</span>
        </div>
        {detections.error && !detections.data
          ? <div className="recommendations-empty" role="alert">Saved detections could not be loaded.</div>
          : detections.busy && !detections.data
          ? <div className="recommendations-empty" role="status">Loading saved detections…</div>
          : filteredRecords.length
            ? <div className="recommendations-grid">{filteredRecords.map((record) => {
              const guidance = recommendationsFor(record)
              const status = getDetectionHealthStatus(record)
              return <article className="card recommendation-detection-card" key={record.id}>
                <div className="recommendation-card-image">
                  {record.image_url
                    ? <img src={api.imageUrl(record.image_url)} alt={`${record.crop_name} leaf from detection`} loading="lazy" />
                    : <div className="recommendation-image-empty"><Leaf size={24} /><span>Image unavailable</span></div>}
                  <span className={`badge ${status === 'Unhealthy' ? 'disease' : ''}`}>{status}</span>
                </div>
                <div className="recommendation-card-content">
                  <div className="recommendation-card-title"><h2>{record.crop_name}</h2></div>
                  <div className="recommendation-confidence-row">
                    <span>Health confidence <strong>{score(record.health_confidence ?? record.prediction_score)}</strong></span>
                    {Number.isFinite(record.crop_confidence) && <span>Crop confidence <strong>{score(record.crop_confidence)}</strong></span>}
                  </div>
                  <div className="recommendation-card-date">{formatDate(record.created_at)}</div>
                  <div className="recommendation-card-source">Source: {record.source === 'live_monitoring' ? 'Live Monitoring' : 'AI Analysis'}</div>
                  <div className="recommendation-card-source">Gemini image analysis: {record.gemini_status === 'completed'
                    ? record.gemini_analysis?.assessment === 'likely_disease'
                      ? `Likely ${record.gemini_analysis.likely_disease}`
                      : record.gemini_analysis?.assessment === 'inconclusive'
                        ? 'Inconclusive'
                        : 'Possible causes identified'
                    : record.gemini_status === 'not_configured'
                      ? 'Not configured'
                      : record.gemini_status === 'running'
                        ? 'Analysis in progress'
                        : 'Retry available'}</div>
                  <p className="recommendation-card-overview">{guidance?.overview}</p>
                  <div className="recommendation-immediate"><strong>First action</strong><span>{guidance.immediateAction}</span></div>
                  <div className="recommendation-card-actions">
                    <button className="button primary" onClick={() => showSolution(record)}>View solution</button>
                    <span className={`recommendation-review-state${record.recommendation_reviewed ? ' reviewed' : ''}`}>
                      {record.recommendation_reviewed ? 'Reviewed' : 'Pending'}
                    </span>
                  </div>
                </div>
              </article>
            })}</div>
            : <div className="recommendations-empty">{records.length === 0
              ? 'No unhealthy detections yet. Analyze a leaf image or start live monitoring to receive crop-specific recommendations.'
              : 'No detections match this crop filter.'}</div>}
      </section>
      {selected && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) closeSolution() }}>
        <section className="modal recommendation-solution-modal" role="dialog" aria-modal="true" aria-labelledby="recommendation-solution-title">
          <div className="modal-header">
            <div><h2 className="card-title" id="recommendation-solution-title">{selected.crop_name} · Unhealthy</h2><div className="recommendations-context">Source: {selected.source === 'live_monitoring' ? 'Live Monitoring' : 'AI Analysis'} · {formatDate(selected.created_at)} · Health confidence {score(selected.health_confidence ?? selected.prediction_score)}{Number.isFinite(selected.crop_confidence) ? ` · Crop confidence ${score(selected.crop_confidence)}` : ''}</div></div>
            <button className="button" onClick={closeSolution}>Close</button>
          </div>
          {selected.image_url && <img className="recommendation-solution-image" src={api.imageUrl(selected.image_url)} alt={`${selected.crop_name} leaf from detection`} />}
          <section className="recommendation-solution-section gemini-analysis-result" aria-label="Gemini image disease assessment">
            <h3>Gemini image assessment</h3>
            {selected.gemini_status === 'completed' && selected.gemini_analysis
              ? <>
                <h4>{selected.gemini_analysis.assessment === 'inconclusive'
                  ? 'Inconclusive — image is not sufficient for a diagnosis'
                  : selected.gemini_analysis.assessment === 'likely_disease'
                    ? `Likely disease: ${selected.gemini_analysis.likely_disease}`
                    : 'Possible causes (not a diagnosis)'}</h4>
                <p>{selected.gemini_analysis.explanation}</p>
                {[
                  ['Possible causes', selected.gemini_analysis.possible_causes],
                  ['Visible symptoms', selected.gemini_analysis.visible_symptoms],
                  ['Immediate actions', selected.gemini_analysis.immediate_actions],
                  ['Treatment and management', selected.gemini_analysis.treatment_management],
                  ['Organic options', selected.gemini_analysis.organic_options],
                  ['Prevention', selected.gemini_analysis.prevention],
                  ['Follow-up monitoring', selected.gemini_analysis.follow_up],
                ].map(([title, items]) => <div key={title}><h4>{title}</h4>{items?.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No image-based guidance returned.</p>}</div>)}
                <h4>When to consult an agricultural expert</h4>
                <p>{selected.gemini_analysis.expert_guidance}</p>
              </>
              : <>
                <p>{selected.gemini_status === 'running'
                  ? 'Gemini analysis is in progress.'
                  : selected.gemini_status === 'failed' && /HTTP (429|503)/.test(selected.gemini_error || '')
                    ? 'Gemini is temporarily unavailable due to high demand. Please retry shortly.'
                    : selected.gemini_error || 'No Gemini image assessment is saved for this detection yet.'}</p>
                <button className="button primary" onClick={() => retryGemini(selected)} disabled={geminiBusyId === selected.id || selected.gemini_status === 'running'}>
                  {geminiBusyId === selected.id ? 'Analyzing image…' : 'Retry Gemini analysis'}
                </button>
              </>}
          </section>
          <h3 className="card-title">Additional crop-specific guidance</h3>
          <div className="recommendation-solution-sections">
            {[
              ['Overview', 'overview'],
              ['Symptoms to inspect', 'symptoms'],
              ['Possible causes (not a diagnosis)', 'possibleCauses'],
              ['Immediate treatment steps', 'immediateActions'],
              ['Organic management options', 'organicManagement'],
              ['Prevention', 'prevention'],
              ['Water and soil management', 'waterAndSoil'],
              ['Safe treatment guidance', 'safeTreatment'],
              ['Follow-up monitoring', 'followUp'],
              ['When to seek expert help', 'expert'],
            ].map(([title, key]) => {
              const value = recommendationsFor(selected)?.[key]
              return <section className="recommendation-solution-section" key={key}>
                <h3>{title}</h3>
                {Array.isArray(value) ? <ul>{value.map((item) => <li key={item}>{item}</li>)}</ul> : <p>{value}</p>}
              </section>
            })}
          </div>
          <div className="recommendation-solution-actions">
            <Link className="button" to={`/history?id=${encodeURIComponent(selected.id)}`} onClick={closeSolution}>View detection record</Link>
            <button className="button primary" onClick={() => markReviewed(selected)} disabled={reviewBusyId === selected.id || selected.recommendation_reviewed}>
              <Check size={14} />{reviewBusyId === selected.id ? 'Saving…' : selected.recommendation_reviewed ? 'Reviewed' : 'Mark as reviewed'}
            </button>
          </div>
        </section>
      </div>}
    </div>
  </>
}

export function SettingsPage() {
  const [saved, setSaved] = useState(false)
  const [backendUrl, setBackendUrl] = useState(api.baseUrl)
  const [cameraEndpoint, setCameraEndpoint] = useState(localStorage.getItem('cameraEndpoint') || '')
  const [refresh, setRefresh] = useState(localStorage.getItem('refreshInterval') || '30000')
  const [mapStyle, setMapStyle] = useState(localStorage.getItem('mapStyle') || 'standard')
  const [formError, setFormError] = useState('')
  const connection = useLoad(() => api.health(), [])
  const save = (event) => {
    event.preventDefault()
    let parsedUrl
    try {
      parsedUrl = new URL(backendUrl.trim())
      if (!['http:', 'https:'].includes(parsedUrl.protocol) || !parsedUrl.hostname || parsedUrl.username || parsedUrl.password || parsedUrl.search || parsedUrl.hash) {
        throw new Error('invalid')
      }
    } catch {
      setFormError('Enter a valid HTTP or HTTPS backend URL.')
      setSaved(false)
      return
    }
    const normalizedUrl = `${parsedUrl.origin}${parsedUrl.pathname.replace(/\/+$/, '')}`
    try {
      if (normalizedUrl === api.defaultBaseUrl) localStorage.removeItem('apiBaseUrl')
      else localStorage.setItem('apiBaseUrl', normalizedUrl)
      localStorage.setItem('cameraEndpoint', cameraEndpoint.trim())
      localStorage.setItem('refreshInterval', refresh)
      localStorage.setItem('mapStyle', mapStyle)
      setBackendUrl(normalizedUrl)
      setFormError('')
      setSaved(true)
      window.setTimeout(() => window.location.reload(), 900)
    } catch {
      setFormError('Unable to save settings in this browser.')
      setSaved(false)
    }
  }
  return <>
    <div className="settings-page">
      <div className="settings-heading"><h1 className="page-title">Settings</h1></div>
      <form onSubmit={save} className="grid settings-layout">
        <section className="card settings-card" aria-labelledby="settings-backend-title">
          <div className="card-heading settings-card-heading">
            <div className="card-title" id="settings-backend-title">Backend configuration</div>
            <div className={`settings-connection ${connection.busy ? 'checking' : connection.error ? 'offline' : 'online'}`} role="status">
              <span className="status-dot" />{connection.busy ? 'Checking' : connection.error ? 'Unavailable' : 'Connected'}
              <button className="button ghost settings-refresh" type="button" onClick={connection.refresh} disabled={connection.busy} aria-label="Refresh connection status"><RefreshCw size={13} /></button>
            </div>
          </div>
          <label className="form-row settings-url-field">
            <span className="form-label">Backend URL</span>
            <input className="field form-input" type="text" inputMode="url" autoCapitalize="none" spellCheck="false" value={backendUrl} onChange={(event) => { setBackendUrl(event.target.value); setSaved(false); setFormError('') }} aria-describedby="backend-url-help" />
            <span className="form-help" id="backend-url-help">Uses the build configuration unless overridden here.</span>
          </label>
          {formError && <div className="settings-feedback error" role="alert">{formError}</div>}
          {saved && <div className="settings-feedback success" role="status">Settings saved.</div>}
        </section>
        <section className="card settings-card" aria-labelledby="settings-preferences-title">
          <div className="card-heading"><div className="card-title" id="settings-preferences-title">Preferences</div></div>
          <label className="form-row"><span className="form-label">Camera endpoint</span><input className="field form-input" type="url" placeholder="http://camera.local/stream" value={cameraEndpoint} onChange={(event) => setCameraEndpoint(event.target.value)} /></label>
          <label className="form-row"><span className="form-label">Status refresh interval</span><select className="select form-input" value={refresh} onChange={(event) => setRefresh(event.target.value)}><option value="10000">10 seconds</option><option value="30000">30 seconds</option><option value="60000">1 minute</option><option value="300000">5 minutes</option></select></label>
          <label className="form-row"><span className="form-label">Map tiles</span><select className="select form-input" value={mapStyle} onChange={(event) => setMapStyle(event.target.value)}><option value="standard">Standard (OpenStreetMap)</option></select></label>
        </section>
        <div className="settings-actions">
          <button className="button primary" type="submit"><Check size={14} />Save settings</button>
          <span className="form-help">Preferences are stored in this browser.</span>
        </div>
      </form>
    </div>
  </>
}
