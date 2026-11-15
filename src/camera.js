export function getCameraConstraints() {
  return {
    audio: false,
    video: { facingMode: { ideal: 'environment' } },
  }
}

export function getCameraErrorMessage(error) {
  if (['NotAllowedError', 'SecurityError'].includes(error?.name)) {
    return 'Camera permission was denied. Allow camera access in your browser settings and try again.'
  }
  if (['NotFoundError', 'DevicesNotFoundError'].includes(error?.name)) {
    return 'No camera was found on this device.'
  }
  if (['NotReadableError', 'TrackStartError'].includes(error?.name)) {
    return 'The camera could not be started. It may already be in use by another app.'
  }
  return 'Unable to access the camera. Check your browser permissions and try again.'
}

export function stopCameraStream(stream) {
  stream?.getTracks().forEach((track) => track.stop())
}
