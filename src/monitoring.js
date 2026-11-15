export async function getLatestDetection(fetchDetections) {
  const response = await fetchDetections({ page: 1, page_size: 1 })
  return response.items?.[0] ?? null
}
