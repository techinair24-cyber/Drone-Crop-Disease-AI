import test from 'node:test'
import assert from 'node:assert/strict'
import { getCropRecommendation, getDetectionHealthStatus } from './recommendationKnowledge.js'
import { SUPPORTED_CROPS } from './supportedCrops.js'

test('every supported crop has complete, crop-specific solution guidance', () => {
  const immediateActions = new Set()
  for (const crop of SUPPORTED_CROPS) {
    const guidance = getCropRecommendation(crop)
    assert.ok(guidance, `${crop} guidance should exist`)
    for (const section of [
      'overview',
      'symptoms',
      'possibleCauses',
      'immediateActions',
      'organicManagement',
      'prevention',
      'waterAndSoil',
      'safeTreatment',
      'followUp',
      'expert',
      'immediateAction',
    ]) {
      assert.ok(guidance[section], `${crop} guidance should include ${section}`)
    }
    immediateActions.add(guidance.immediateAction)
  }
  assert.equal(immediateActions.size, SUPPORTED_CROPS.length)
})

test('recommendation lookup rejects unknown crops', () => {
  assert.equal(getCropRecommendation('Unknown'), null)
})

test('detection status supports current and legacy history records', () => {
  assert.equal(getDetectionHealthStatus({ health_status: 'Healthy' }), 'Healthy')
  assert.equal(getDetectionHealthStatus({ classification: 'healthy' }), 'Healthy')
  assert.equal(getDetectionHealthStatus({ health_status: 'Unhealthy' }), 'Unhealthy')
  assert.equal(getDetectionHealthStatus({ classification: 'diseased' }), 'Unhealthy')
  assert.equal(getDetectionHealthStatus({ classification: 'inconclusive' }), null)
})
