import assert from 'node:assert/strict'
import test from 'node:test'
import { api } from './api.js'
import { fetchEsp32Photo, getEsp32CamEndpoints } from './camera.js'
import { predictCrop } from './cropPrediction.js'
import { SUPPORTED_CROPS } from './supportedCrops.js'

const file = { name: 'leaf.jpg' }
const location = { latitude: 12, longitude: 34 }

function createApi(cropName, healthStatus = 'Healthy') {
  const calls = []
  return {
    calls,
    predict: async (...args) => {
      calls.push(args)
      const healthProbabilities = {
        Healthy: healthStatus === 'Healthy' ? 0.8 : 0.2,
        Unhealthy: healthStatus === 'Unhealthy' ? 0.8 : 0.2,
      }
      return {
        id: 'prediction-id',
        crop_name: cropName,
        crop_confidence: 0.95,
        health_status: healthStatus,
        health_confidence: 0.8,
        health_probabilities: healthProbabilities,
        message: `${cropName} classified as ${healthStatus}.`,
        classification: healthStatus === 'Healthy' ? 'healthy' : 'diseased',
        prediction_score: 0.8,
        top_predictions: Object.entries(healthProbabilities).map(
          ([label, score]) => ({ label, score })
        ),
      }
    },
  }
}

test('sends each manually selected crop through full prediction with its source', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop, 'Unhealthy')
    const result = await predictCrop(api, file, crop, location)

    assert.deepEqual(api.calls, [[file, crop, location, 'analysis']])
    assert.equal(result.crop_name, crop)
    assert.equal(result.health_status, 'Unhealthy')
    assert.equal(result.crop_confidence, 0.95)
    assert.equal(result.health_confidence, 0.8)
  }
})

test('rejects Object (Non-Leaf) without requesting prediction', async () => {
  const api = createApi('Apple')

  await assert.rejects(
    predictCrop(api, file, 'Object', location),
    { message: 'Image Rejected: No crop leaf selected for analysis.' }
  )
  assert.equal(api.calls.length, 0)
})

test('sends automatic selection through full crop and health prediction', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop)
    const result = await predictCrop(api, file, '', location)

    assert.deepEqual(api.calls, [[file, '', location, 'analysis']])
    assert.equal(result.crop_name, crop)
    assert.ok(['Healthy', 'Unhealthy'].includes(result.health_status))
  }
})

test('records Monitor predictions with live-monitoring source', async () => {
  const api = createApi('Apple', 'Unhealthy')
  const result = await predictCrop(api, file, '', location, 'live_monitoring')

  assert.deepEqual(api.calls, [[file, '', location, 'live_monitoring']])
  assert.equal(result.health_status, 'Unhealthy')
})

test('sends an ESP32-CAM capture through the existing analysis prediction pipeline', async () => {
  const originalFetch = globalThis.fetch
  const originalStorage = globalThis.localStorage
  let predictionRequest
  globalThis.localStorage = { getItem: () => null }
  try {
    const endpoints = getEsp32CamEndpoints()
    const image = new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xd9])], { type: 'image/jpeg' })
    const capturedBlob = await fetchEsp32Photo(endpoints.capture, {
      fetchImpl: async (url) => {
        assert.equal(url, `${api.defaultBaseUrl}/api/camera/capture`)
        return new Response(image, { status: 200 })
      },
    })
    const capturedFile = new File([capturedBlob], 'esp32-crop-photo.jpg', { type: capturedBlob.type })
    globalThis.fetch = async (url, options) => {
      predictionRequest = { url, options }
      return new Response(JSON.stringify({
        crop_name: 'Apple',
        crop_confidence: 0.95,
        health_status: 'Healthy',
        health_confidence: 0.8,
        health_probabilities: { Healthy: 0.8, Unhealthy: 0.2 },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }

    const result = await predictCrop(api, capturedFile, 'Apple', location, 'analysis')

    assert.equal(result.health_status, 'Healthy')
    assert.equal(predictionRequest.url, `${api.defaultBaseUrl}/api/predict`)
    assert.equal(predictionRequest.options.body.get('file').name, capturedFile.name)
    assert.equal(predictionRequest.options.body.get('file').type, 'image/jpeg')
    assert.equal(await predictionRequest.options.body.get('file').text(), await capturedFile.text())
    assert.equal(predictionRequest.options.body.get('crop_name'), 'Apple')
    assert.equal(predictionRequest.options.body.get('source'), 'analysis')
  } finally {
    globalThis.fetch = originalFetch
    if (originalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalStorage
  }
})

test('rejects invalid manual selection before requesting prediction', async () => {
  const api = createApi('Apple')

  await assert.rejects(
    predictCrop(api, file, 'Unknown Crop', location),
    /selected crop is not supported/
  )
  assert.equal(api.calls.length, 0)
})

test('rejects incomplete or invalid health results instead of showing crop-only success', async () => {
  const incompleteApi = {
    predict: async () => ({ crop_name: 'Apple', crop_confidence: 0.9 }),
  }
  await assert.rejects(
    predictCrop(incompleteApi, file, '', location),
    /valid health classification/
  )

  const invalidConfidenceApi = {
    predict: async () => ({
      crop_name: 'Apple',
      crop_confidence: 0.9,
      health_status: 'Healthy',
      health_confidence: 1.2,
      health_probabilities: { Healthy: 1.2, Unhealthy: -0.2 },
    }),
  }
  await assert.rejects(
    predictCrop(invalidConfidenceApi, file, '', location),
    /invalid confidence/
  )
})
