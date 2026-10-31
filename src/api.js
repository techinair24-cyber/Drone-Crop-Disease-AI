const DEFAULT_API_BASE = (import.meta.env.VITE_API_BASE_URL || 'https://drone-crop-disease-ai.onrender.com').replace(/\/+$/, '')
const API_BASE_STORAGE_KEY = 'apiBaseUrl'

function getApiBase() {
  return (localStorage.getItem(API_BASE_STORAGE_KEY) || DEFAULT_API_BASE).replace(/\/+$/, '')
}

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${getApiBase()}${path}`, options)
  } catch {
    throw new ApiError('Cannot reach the backend. Check that the API is running and VITE_API_BASE_URL is correct.')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(body.detail || body.message || `Request failed (${response.status}).`, response.status)
  }
  return body
}

export const api = {
  defaultBaseUrl: DEFAULT_API_BASE,
  get baseUrl() {
    return getApiBase()
  },
  health: () => request('/health'),
  status: () => request('/api/status'),
  stats: () => request('/api/stats'),
  detections: (params = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) query.set(key, value)
    })
    return request(`/api/detections${query.size ? `?${query}` : ''}`)
  },
  detection: (id) => request(`/api/detections/${encodeURIComponent(id)}`),
  locations: (params = {}) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) query.set(key, value)
    })
    return request(`/api/locations${query.size ? `?${query}` : ''}`)
  },
  allLocations: async (params = {}) => {
    const items = []
    let page = 1
    let pages = 1
    do {
      const result = await api.locations({ ...params, page, page_size: 500 })
      items.push(...result.items)
      pages = result.pages
      page += 1
    } while (page <= pages)
    return items
  },
  predict: (file, cropName = '', location = null) => {
    const form = new FormData()
    form.append('file', file)
    if (cropName) form.append('crop_name', cropName)
    if (location) {
      form.append('latitude', location.latitude)
      form.append('longitude', location.longitude)
    }
    return request('/api/predict', { method: 'POST', body: form })
  },
  imageUrl: (path) => path?.startsWith('http') ? path : `${getApiBase()}${path || ''}`,
}

export async function exportDetections(params = {}) {
  const all = []
  let page = 1
  let totalPages = 1
  do {
    const result = await api.detections({ ...params, page, page_size: 100 })
    all.push(...result.items)
    totalPages = result.pages
    page += 1
  } while (page <= totalPages)
  if (!all.length) throw new ApiError('There are no records to export.')
  const columns = ['crop_name', 'disease_name', 'classification', 'prediction_score', 'created_at', 'model_name']
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const csv = [
    columns.join(','),
    ...all.map((row) => columns.map((column) => {
      const value = column === 'model_name'
        ? String(row[column] ?? '').replace(/\bprototype\b/ig, '').replace(/\s{2,}/g, ' ').trim()
        : row[column]
      return escape(value)
    }).join(',')),
  ].join('\r\n')
  const link = document.createElement('a')
  const objectUrl = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  link.href = objectUrl
  link.download = `dronecrop-detections-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}
