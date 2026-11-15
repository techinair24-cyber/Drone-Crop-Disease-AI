function cameraEndpointError(route, cause) {
  if (cause?.name === 'AbortError') {
    return new Error(`The ESP32-CAM ${route} request timed out.`)
  }
  if (cause instanceof TypeError) {
    return new Error(
      `The browser could not reach ESP32-CAM ${route}. Check for HTTPS-to-HTTP mixed-content blocking, camera CORS settings, and local-network access permissions.`,
    )
  }
  return new Error(`The ESP32-CAM ${route} request failed.`)
}

async function requestCameraEndpoint(url, route, { fetchImpl = globalThis.fetch, signal } = {}) {
  let response
  try {
    response = await fetchImpl(url, { method: 'GET', cache: 'no-store', signal })
  } catch (cause) {
    throw cameraEndpointError(route, cause)
  }
  if (!response.ok) {
    throw new Error(`The ESP32-CAM ${route} endpoint returned HTTP ${response.status}.`)
  }
  return response
}

export function getEsp32CamEndpoints(configuredEndpoint) {
  if (typeof configuredEndpoint !== 'string' || !configuredEndpoint.trim()) {
    throw new Error('Configure the ESP32-CAM endpoint in Settings.')
  }

  let url
  try {
    url = new URL(configuredEndpoint.trim())
  } catch {
    throw new Error('Enter a valid ESP32-CAM HTTP or HTTPS endpoint in Settings.')
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('The ESP32-CAM endpoint must be an HTTP or HTTPS URL without embedded credentials.')
  }

  const configuredPath = url.pathname.replace(/\/+$/, '')
  const basePath = configuredPath.replace(/\/(?:stream|capture|status)$/i, '')
  const query = url.search
  const stream = /\/stream$/i.test(configuredPath)
    ? `${url.origin}${configuredPath}${query}`
    : `${url.protocol}//${url.hostname}:81${basePath}/stream${query}`
  const port80Base = `http://${url.hostname}:80${basePath}`
  return {
    stream,
    capture: `${port80Base}/capture${query}`,
    status: `${port80Base}/status${query}`,
  }
}

export async function fetchEsp32Photo(url, options = {}) {
  const response = await requestCameraEndpoint(url, '/capture', options)
  let blob
  try {
    blob = await response.blob()
  } catch (cause) {
    throw cameraEndpointError('/capture image body', cause)
  }
  const type = blob.type.split(';')[0].trim().toLowerCase()
  if (!blob.size || !['image/jpeg', 'image/png'].includes(type)) {
    throw new Error('The ESP32-CAM /capture endpoint did not return a JPG or PNG image.')
  }
  return blob
}

export async function checkEsp32Status(url, options = {}) {
  await requestCameraEndpoint(url, '/status', options)
}
