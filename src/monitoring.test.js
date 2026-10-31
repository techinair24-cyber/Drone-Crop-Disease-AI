import assert from 'node:assert/strict'
import test from 'node:test'
import { getLatestDetection, MONITOR_REFRESH_INTERVAL_MS, scheduleMonitorRefresh } from './monitoring.js'
import { SUPPORTED_CROPS } from './supportedCrops.js'

test('gets the newest detection and its image URL', async () => {
  const latest = { id: 'latest', image_url: '/api/images/latest.jpg' }
  const older = { id: 'older', image_url: '/api/images/older.jpg' }
  let query

  const detection = await getLatestDetection(async (params) => {
    query = params
    return { items: [latest, older] }
  })

  assert.deepEqual(query, { page: 1, page_size: 1 })
  assert.equal(detection, latest)
  assert.equal(detection.image_url, '/api/images/latest.jpg')
})

test('returns no detection when the backend has no uploaded image', async () => {
  assert.equal(await getLatestDetection(async () => ({ items: [] })), null)
})

test('schedules monitor refresh every 30 seconds', () => {
  const refresh = () => {}
  let scheduled
  const timer = scheduleMonitorRefresh(refresh, (callback, delay) => {
    scheduled = { callback, delay }
    return 17
  })

  assert.equal(scheduled.callback, refresh)
  assert.equal(scheduled.delay, 30_000)
  assert.equal(scheduled.delay, MONITOR_REFRESH_INTERVAL_MS)
  assert.equal(timer, 17)
})

test('exposes no more than ten selectable crop types', () => {
  assert.equal(SUPPORTED_CROPS.length, 9)
  assert.equal(SUPPORTED_CROPS.includes('Blueberry'), false)
  assert.equal(SUPPORTED_CROPS.includes('Tomato'), true)
})
