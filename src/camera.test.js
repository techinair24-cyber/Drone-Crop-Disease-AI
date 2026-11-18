import assert from 'node:assert/strict'
import test from 'node:test'
import { fetchEsp32Photo, getEsp32CamEndpoints } from './camera.js'

function withBackendUrl(url, callback) {
  const originalStorage = globalThis.localStorage
  globalThis.localStorage = {
    getItem: (key) => key === 'apiBaseUrl' ? url : null,
  }

  try {
    return callback()
  } finally {
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  }
}

test('builds camera proxy URLs from the configured backend', () => {
  const endpoints = withBackendUrl(
    'https://api.example.test/',
    () => getEsp32CamEndpoints(),
  )

  assert.deepEqual(endpoints, {
    stream: 'https://api.example.test/api/camera/stream',
    capture: 'https://api.example.test/api/camera/capture',
  })
})

test('fetches a real image from the backend camera capture route', async () => {
  const endpoints = withBackendUrl(
    'https://api.example.test',
    () => getEsp32CamEndpoints(),
  )
  const requests = []
  const jpeg = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], {
    type: 'image/jpeg',
  })
  const photo = await fetchEsp32Photo(endpoints.capture, {
    fetchImpl: async (...args) => {
      requests.push(args)
      return new Response(jpeg, { status: 200 })
    },
  })

  assert.equal(photo.type, 'image/jpeg')
  assert.equal(photo.size, jpeg.size)
  assert.equal(requests[0][0], 'https://api.example.test/api/camera/capture')
  assert.equal(requests[0][1].method, 'GET')
  assert.equal(requests[0][1].cache, 'no-store')
})

test('rejects invalid images and unsuccessful capture responses', async () => {
  await assert.rejects(
    fetchEsp32Photo('https://api.example.test/api/camera/capture', {
      fetchImpl: async () => new Response('offline', {
        status: 200,
        headers: { 'Content-Type': 'text/plain' },
      }),
    }),
    /did not return a valid JPG or PNG image/,
  )
  await assert.rejects(
    fetchEsp32Photo('https://api.example.test/api/camera/capture', {
      fetchImpl: async () => new Response('offline', { status: 503 }),
    }),
    /endpoint returned HTTP 503/,
  )
})

test('reports capture network failures and timeouts', async () => {
  await assert.rejects(
    fetchEsp32Photo('https://api.example.test/api/camera/capture', {
      fetchImpl: async () => { throw new TypeError('Failed to fetch') },
    }),
    /endpoint could not be reached/,
  )

  const timeout = new Error('aborted')
  timeout.name = 'AbortError'
  await assert.rejects(
    fetchEsp32Photo('https://api.example.test/api/camera/capture', {
      fetchImpl: async () => { throw timeout },
    }),
    /capture request timed out/,
  )
})
