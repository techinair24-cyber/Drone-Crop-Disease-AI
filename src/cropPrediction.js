import { SUPPORTED_CROPS } from './supportedCrops.js'

export function getCropSelectionError(selectedCrop) {
  if (selectedCrop === 'Object') {
    return new Error('Image Rejected: No crop leaf selected for analysis.')
  }
  if (selectedCrop && !SUPPORTED_CROPS.includes(selectedCrop)) {
    return new Error('The selected crop is not supported.')
  }
  return null
}

export async function predictCrop(
  api,
  file,
  selectedCrop,
  location,
  source = 'analysis',
) {
  const selectionError = getCropSelectionError(selectedCrop)
  if (selectionError) throw selectionError

  const result = await api.predict(file, selectedCrop, location, source)
  if (!SUPPORTED_CROPS.includes(result?.crop_name)) {
    throw new Error('Prediction returned an unsupported crop.')
  }
  if (!['Healthy', 'Unhealthy'].includes(result.health_status)) {
    throw new Error('Prediction did not include a valid health classification.')
  }

  for (const confidence of [
    result.crop_confidence,
    result.health_confidence,
    result.health_probabilities?.Healthy,
    result.health_probabilities?.Unhealthy,
  ]) {
    if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
      throw new Error('Prediction returned an invalid confidence value.')
    }
  }

  return result
}
