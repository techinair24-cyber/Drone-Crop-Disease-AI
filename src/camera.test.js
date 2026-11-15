import assert from 'node:assert/strict'
import test from 'node:test'
import { checkEsp32Status, fetchEsp32Photo, getEsp32CamEndpoints } from './camera.js'

test('builds firmware route URLs from the configured ESP32-CAM endpoint', () => {
  assert.deepEqual(getEsp32CamEndpoints('http://esp.local:81/stream'), {
    stream: 'http://esp.local:81/stream',
    capture: 'http://esp.local:80/capture',
    status: 'http://esp.local:80/status',
  })
  assert.deepEqual(getEsp32CamEndpoints('https://esp.local/camera/capture?token=abc'), {
    stream: 'https://esp.local:81/camera/stream?token=abc',
    capture: 'http://esp.local:80/camera/capture?token=abc',
    status: 'http://esp.local:80/camera/status?token=abc',
  })
  assert.deepEqual(getEsp32CamEndpoints('http://esp.local'), {
    stream: 'http://esp.local:81/stream',
    capture: 'http://esp.local:80/capture',
    status: 'http://esp.local:80/status',
  })
})

test('rejects missing and insecurely formed ESP32-CAM settings', () => {
  assert.throws(() => getEsp32CamEndpoints(''), /Configure the ESP32-CAM endpoint/)
  assert.throws(() => getEsp32CamEndpoints('not a URL'), /valid ESP32-CAM/)
  assert.throws(() => getEsp32CamEndpoints('ftp://esp.local'), /HTTP or HTTPS/)
  assert.throws(() => getEsp32CamEndpoints('http://user:pass@esp.local'), /without embedded credentials/)
})

test('fetches a real image from the configured /capture route', async () => {
  const requests = []
  const jpeg = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: 'image/jpeg' })
  const photo = await fetchEsp32Photo('http://esp.local:80/capture', {
    fetchImpl: async (...args) => {
      requests.push(args)
      return new Response(jpeg, { status: 200 })
    },
  })

  assert.equal(photo.type, 'image/jpeg')
  assert.equal(photo.size, jpeg.size)
  assert.equal(requests[0][0], 'http://esp.local:80/capture')
  assert.equal(requests[0][1].method, 'GET')
  assert.equal(requests[0][1].cache, 'no-store')
})

test('rejects non-image capture responses and failed camera endpoints', async () => {
  await assert.rejects(
    fetchEsp32Photo('http://esp.local:80/capture', {
      fetchImpl: async () => new Response('offline', { status: 200, headers: { 'Content-Type': 'text/plain' } }),
    }),
    /did not return a JPG or PNG image/
  )
  await assert.rejects(
    fetchEsp32Photo('http://esp.local:80/capture', {
      fetchImpl: async () => new Response('offline', { status: 503 }),
    }),
    /HTTP 503/
  )
})

test('reports browser network restrictions and checks the configured /status route', async () => {
  await assert.rejects(
    fetchEsp32Photo('http://esp.local:80/capture', {
      fetchImpl: async () => { throw new TypeError('Failed to fetch') },
    }),
    /mixed-content blocking.*CORS.*local-network access/
  )

  const requests = []
  await checkEsp32Status('http://esp.local:80/status', {
    fetchImpl: async (...args) => {
      requests.push(args)
      return new Response('{}', { status: 200 })
    },
  })
  assert.equal(requests[0][0], 'http://esp.local:80/status')
  assert.equal(requests[0][1].method, 'GET')
})

test('reports capture timeouts and unsuccessful /status responses', async () => {
  const timeout = new Error('aborted')
  timeout.name = 'AbortError'
  await assert.rejects(
    fetchEsp32Photo('http://esp.local:80/capture', {
      fetchImpl: async () => { throw timeout },
    }),
    /capture request timed out/
  )
  await assert.rejects(
    checkEsp32Status('http://esp.local:80/status', {
      fetchImpl: async () => new Response('unavailable', { status: 503 }),
    }),
    /\/status endpoint returned HTTP 503/
  )
})
