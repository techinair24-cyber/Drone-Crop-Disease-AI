import assert from 'node:assert/strict'
import test from 'node:test'
import { getCurrentLocation, hasValidCoordinates } from './location.js'

test('accepts a valid coordinate pair for map display without GPS metadata', () => {
  assert.equal(hasValidCoordinates({
    latitude: 12.4,
    longitude: 76.2,
    gps_fix_valid: null,
  }), true)
})

test('rejects coordinates outside valid latitude and longitude ranges', () => {
  assert.equal(hasValidCoordinates({ latitude: 91, longitude: 76.2 }), false)
  assert.equal(hasValidCoordinates({ latitude: 12.4, longitude: -181 }), false)
})

test('gets current coordinates after location permission is granted', async () => {
  const options = []
  const navigatorObject = {
    permissions: { query: async () => ({ state: 'granted' }) },
    geolocation: {
      getCurrentPosition(success, _error, requestOptions) {
        options.push(requestOptions)
        success({ coords: { latitude: 12.4, longitude: 76.2 } })
      },
    },
  }

  assert.deepEqual(await getCurrentLocation(navigatorObject), {
    coordinates: { latitude: 12.4, longitude: 76.2 },
    message: 'Current location added to this detection.',
  })
  assert.equal(options.length, 1)
  assert.equal(options[0].timeout, 10000)
})

test('does not request geolocation again when permission is denied', async () => {
  let locationRequests = 0
  const navigatorObject = {
    permissions: { query: async () => ({ state: 'denied' }) },
    geolocation: {
      getCurrentPosition() {
        locationRequests += 1
      },
    },
  }

  assert.deepEqual(await getCurrentLocation(navigatorObject), {
    coordinates: null,
    message: 'Location permission was denied. The image was analyzed without location.',
  })
  assert.equal(locationRequests, 0)
})

test('continues without location when permission is denied by geolocation', async () => {
  const navigatorObject = {
    permissions: { query: async () => ({ state: 'prompt' }) },
    geolocation: {
      getCurrentPosition(_success, error) {
        error({ code: 1 })
      },
    },
  }

  assert.deepEqual(await getCurrentLocation(navigatorObject), {
    coordinates: null,
    message: 'Location permission was denied. The image was analyzed without location.',
  })
})

test('continues without invalid coordinates', async () => {
  const navigatorObject = {
    geolocation: {
      getCurrentPosition(success) {
        success({ coords: { latitude: 91, longitude: 76.2 } })
      },
    },
  }

  assert.deepEqual(await getCurrentLocation(navigatorObject), {
    coordinates: null,
    message: 'Location could not be determined. The image was analyzed without location.',
  })
})

test('continues without location when the request times out', async () => {
  const navigatorObject = {
    geolocation: {
      getCurrentPosition(_success, error) {
        error({ code: 3 })
      },
    },
  }

  assert.deepEqual(await getCurrentLocation(navigatorObject), {
    coordinates: null,
    message: 'Location could not be determined. The image was analyzed without location.',
  })
})
