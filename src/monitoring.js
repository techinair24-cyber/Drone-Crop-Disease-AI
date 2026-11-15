export const MONITOR_REFRESH_INTERVAL_MS = 30_000

export async function getLatestDetection(fetchDetections) {
  const response = await fetchDetections({ page: 1, page_size: 1 })
  return response.items?.[0] ?? null
}

export function captureCameraFrame(image, canvas = globalThis.document?.createElement('canvas')) {
  if (!image?.naturalWidth || !image.naturalHeight) {
    return Promise.reject(new Error('The ESP32-CAM stream has no available frame to capture.'))
  }
  if (!canvas) return Promise.reject(new Error('A browser canvas is required to capture the ESP32-CAM frame.'))

  canvas.width = image.naturalWidth
  canvas.height = image.naturalHeight
  const context = canvas.getContext('2d')
  if (!context) return Promise.reject(new Error('Unable to prepare the ESP32-CAM frame for capture.'))
  context.drawImage(image, 0, 0, canvas.width, canvas.height)

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('The ESP32-CAM frame could not be captured.'))
    }, 'image/jpeg', 0.92)
  })
}

export function scheduleMonitorRefresh(refresh, schedule = globalThis.setInterval) {
  return schedule(refresh, MONITOR_REFRESH_INTERVAL_MS)
}
