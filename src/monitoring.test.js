import assert from 'node:assert/strict'
import test from 'node:test'
import {
  captureCameraFrame,
  getLatestDetection,
  MONITOR_REFRESH_INTERVAL_MS,
  scheduleMonitorRefresh,
} from './monitoring.js'
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

test('captures the current frame dimensions from the configured camera image', async () => {
  const calls = []
  const blob = new Blob(['jpeg-frame'], { type: 'image/jpeg' })
  const image = { naturalWidth: 640, naturalHeight: 480 }
  const canvas = {
    getContext: () => ({ drawImage: (...args) => calls.push(args) }),
    toBlob: (callback, type, quality) => {
      calls.push([type, quality])
      callback(blob)
    },
  }

  const result = await captureCameraFrame(image, canvas)

  assert.equal(canvas.width, 640)
  assert.equal(canvas.height, 480)
  assert.deepEqual(calls, [[image, 0, 0, 640, 480], ['image/jpeg', 0.92]])
  assert.equal(result, blob)
})

test('rejects capture when the ESP32-CAM has no loaded frame', async () => {
  await assert.rejects(
    captureCameraFrame({ naturalWidth: 0, naturalHeight: 0 }, {}),
    /no available frame/
  )
})

test('reports capture failure when a browser canvas is unavailable', async () => {
  await assert.rejects(
    captureCameraFrame({ naturalWidth: 640, naturalHeight: 480 }),
    /browser canvas is required/
  )
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

test('exposes all supported crop classes for selection', () => {
  assert.deepEqual(SUPPORTED_CROPS, [
    'Apple',
    'Chilli',
    'Grape',
    'Hibiscus',
    'Maize',
    'Peach',
    'Potato',
    'Strawberry',
    'Tomato',
    'Wheat',
  ])
})
