export const MONITOR_REFRESH_INTERVAL_MS = 30_000

export async function getLatestDetection(fetchDetections) {
  const response = await fetchDetections({ page: 1, page_size: 1 })
  return response.items?.[0] ?? null
}

export function scheduleMonitorRefresh(refresh, schedule = globalThis.setInterval) {
  return schedule(refresh, MONITOR_REFRESH_INTERVAL_MS)
}
