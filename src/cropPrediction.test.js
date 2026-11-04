import assert from 'node:assert/strict'
import test from 'node:test'
import { predictCrop } from './cropPrediction.js'
import { SUPPORTED_CROPS } from './supportedCrops.js'

const file = { name: 'leaf.jpg' }
const location = { latitude: 12, longitude: 34 }

function createApi(detectedCrop) {
  const calls = []
  return {
    calls,
    cropPredict: async (image) => {
      calls.push(['cropPredict', image])
      return {
        crop_name: detectedCrop,
        prediction_score: 0.91,
        top_predictions: [{ label: detectedCrop, score: 0.91 }],
      }
    },
    predict: async (...args) => {
      calls.push(['predict', ...args])
      return {
        crop_name: 'Hibiscus',
        disease_name: 'Healthy',
        prediction_score: 0.88,
        top_predictions: [{ label: 'Healthy', score: 0.88 }],
      }
    },
  }
}

test('validates each manual crop against crop detection before disease prediction', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop)
    const result = await predictCrop(api, file, crop, location)

    assert.equal(result.crop_name, crop)
    assert.equal(result.crop_confidence, 0.91)
    assert.equal(api.calls[0][0], 'cropPredict')

    if (crop === 'Hibiscus') {
      assert.equal(result.disease_name, 'Healthy')
      assert.deepEqual(api.calls[1], ['predict', file, 'Hibiscus', location])
    } else {
      assert.equal(result.crop_only, true)
      assert.equal(api.calls.length, 1)
    }
  }
})

test('automatic detection uses crop detection for all supported crops', async () => {
  for (const crop of SUPPORTED_CROPS) {
    const api = createApi(crop)
    const result = await predictCrop(api, file, '', location)

    assert.equal(result.crop_name, crop)
    assert.equal(result.crop_confidence, 0.91)
    assert.equal(api.calls[0][0], 'cropPredict')

    if (crop === 'Hibiscus') {
      assert.equal(result.disease_name, 'Healthy')
      assert.equal(api.calls.length, 2)
    } else {
      assert.equal(result.crop_only, true)
      assert.equal(api.calls.length, 1)
    }
  }
})

test('reports manual crop mismatches without calling the Hibiscus disease endpoint', async () => {
  for (let index = 0; index < SUPPORTED_CROPS.length; index += 1) {
    const selectedCrop = SUPPORTED_CROPS[index]
    const detectedCrop = SUPPORTED_CROPS[(index + 1) % SUPPORTED_CROPS.length]
    const api = createApi(detectedCrop)
    const result = await predictCrop(api, file, selectedCrop, location)

    assert.equal(result.crop_only, true)
    assert.equal(result.crop_mismatch, true)
    assert.equal(result.selected_crop, selectedCrop)
    assert.equal(result.crop_name, detectedCrop)
    assert.equal(api.calls.length, 1)
    assert.equal(api.calls[0][0], 'cropPredict')
  }
})

test('rejects unsupported crop detection output', async () => {
  const api = createApi('Unknown crop')
  await assert.rejects(
    predictCrop(api, file, '', location),
    /Crop detection returned an unsupported crop/
  )
  assert.equal(api.calls.length, 1)
})
