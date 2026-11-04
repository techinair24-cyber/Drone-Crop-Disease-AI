import assert from 'node:assert/strict'
import test from 'node:test'
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

test('sends each manually selected crop through full prediction', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop, 'Unhealthy')
    const result = await predictCrop(api, file, crop, location)

    assert.deepEqual(api.calls, [[file, crop, location]])
    assert.equal(result.crop_name, crop)
    assert.equal(result.health_status, 'Unhealthy')
    assert.equal(result.crop_confidence, 0.95)
    assert.equal(result.health_confidence, 0.8)
  }
})

test('sends automatic selection through full crop and health prediction', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop)
    const result = await predictCrop(api, file, '', location)

    assert.deepEqual(api.calls, [[file, '', location]])
    assert.equal(result.crop_name, crop)
    assert.ok(['Healthy', 'Unhealthy'].includes(result.health_status))
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
