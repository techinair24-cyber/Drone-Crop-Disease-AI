
import { api } from './api.js'

function cameraEndpointError(route, cause) {
  if (cause?.name === 'AbortError') {
    return new Error(`The camera ${route} request timed out.`)
  }

  if (cause instanceof TypeError) {
    return new Error(`The Render camera ${route} endpoint could not be reached.`)
  }

  return new Error(`The camera ${route} request failed.`)
}

function getCameraBaseUrl() {
  const base = api.baseUrl?.replace(/\/+$/, '')

  if (!base) {
    throw new Error('The backend URL is not configured.')
  }

  return `${base}/api/camera`
}

async function requestCameraEndpoint(url, route, {
  fetchImpl = globalThis.fetch,
  signal,
} = {}) {
  let response

  try {
    response = await fetchImpl(url, {
      method: 'GET',
      cache: 'no-store',
      signal,
    })
  } catch (cause) {
    throw cameraEndpointError(route, cause)
  }

  if (!response.ok) {
    throw new Error(
      `The backend camera ${route} endpoint returned HTTP ${response.status}.`,
    )
  }

  return response
}

export function getEsp32CamEndpoints() {
  const base = getCameraBaseUrl()

  return {
    stream: `${base}/stream`,
    capture: `${base}/capture`,
    status: `${base}/status`,
  }
}

export async function fetchEsp32Photo(url, options = {}) {
  const response = await requestCameraEndpoint(
    url,
    '/capture',
    options,
  )

  let blob

  try {
    blob = await response.blob()
  } catch (cause) {
    throw cameraEndpointError('/capture image body', cause)
  }

  const type = blob.type.split(';')[0].trim().toLowerCase()

  if (!blob.size || !['image/jpeg', 'image/png'].includes(type)) {
    throw new Error('The camera did not return a valid JPG or PNG image.')
  }

  return blob
}

export async function checkEsp32Status(url, options = {}) {
  const response = await requestCameraEndpoint(
    url,
    '/status',
    options,
  )

  return response.json()
}
