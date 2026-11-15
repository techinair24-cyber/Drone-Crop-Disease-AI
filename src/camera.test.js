import assert from 'node:assert/strict'
import test from 'node:test'
import { getCameraConstraints, getCameraErrorMessage, stopCameraStream } from './camera.js'

test('prefers a rear-facing camera and does not request audio', () => {
  assert.deepEqual(getCameraConstraints(), {
    audio: false,
    video: { facingMode: { ideal: 'environment' } },
  })
})

test('provides clear camera permission and availability errors', () => {
  assert.match(getCameraErrorMessage({ name: 'NotAllowedError' }), /permission was denied/i)
  assert.match(getCameraErrorMessage({ name: 'NotFoundError' }), /no camera was found/i)
  assert.match(getCameraErrorMessage({ name: 'NotReadableError' }), /may already be in use/i)
})

test('stops every track when releasing a camera stream', () => {
  const stopped = []
  const stream = {
    getTracks: () => [{ stop: () => stopped.push('video') }, { stop: () => stopped.push('audio') }],
  }

  stopCameraStream(stream)

  assert.deepEqual(stopped, ['video', 'audio'])
  assert.doesNotThrow(() => stopCameraStream(null))
})
