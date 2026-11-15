import assert from 'node:assert/strict'
import test from 'node:test'
import { getLatestDetection } from './monitoring.js'
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
