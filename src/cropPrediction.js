import { SUPPORTED_CROPS } from './supportedCrops.js'

export async function predictCrop(api, file, selectedCrop, location) {
  if (selectedCrop && !SUPPORTED_CROPS.includes(selectedCrop)) {
    throw new Error('The selected crop is not supported.')
  }

  const cropResult = await api.cropPredict(file)
  if (!SUPPORTED_CROPS.includes(cropResult?.crop_name)) {
    throw new Error('Crop detection returned an unsupported crop.')
  }

  const cropPrediction = {
    crop_name: cropResult.crop_name,
    crop_confidence: cropResult.prediction_score,
  }

  if (selectedCrop && cropResult.crop_name !== selectedCrop) {
    return {
      ...cropResult,
      ...cropPrediction,
      crop_only: true,
      crop_mismatch: true,
      selected_crop: selectedCrop,
    }
  }

  if (cropResult.crop_name !== 'Hibiscus') {
    return {
      ...cropResult,
      ...cropPrediction,
      crop_only: true,
    }
  }

  const diseaseResult = await api.predict(file, cropResult.crop_name, location)
  return {
    ...diseaseResult,
    ...cropPrediction,
  }
}
