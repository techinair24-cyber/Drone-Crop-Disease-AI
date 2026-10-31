const PERMISSION_DENIED = 'Location permission was denied. The image was analyzed without location.'
const LOCATION_UNAVAILABLE = 'Location could not be determined. The image was analyzed without location.'

export function hasValidCoordinates({ latitude, longitude }) {
  return Number.isFinite(latitude) && latitude >= -90 && latitude <= 90
    && Number.isFinite(longitude) && longitude >= -180 && longitude <= 180
}

export async function getCurrentLocation(navigatorObject = globalThis.navigator) {
  const geolocation = navigatorObject?.geolocation
  if (!geolocation?.getCurrentPosition) {
    return { coordinates: null, message: LOCATION_UNAVAILABLE }
  }

  try {
    const permission = await navigatorObject.permissions?.query({ name: 'geolocation' })
    if (permission?.state === 'denied') {
      return { coordinates: null, message: PERMISSION_DENIED }
    }
  } catch {
    // Continue with getCurrentPosition when the Permissions API is unavailable.
  }

  return new Promise((resolve) => {
    const unavailable = () => resolve({ coordinates: null, message: LOCATION_UNAVAILABLE })
    try {
      geolocation.getCurrentPosition(
        ({ coords }) => {
          const { latitude, longitude } = coords
          if (!hasValidCoordinates({ latitude, longitude })) {
            unavailable()
            return
          }
          resolve({
            coordinates: { latitude, longitude },
            message: 'Current location added to this detection.',
          })
        },
        (error) => resolve({
          coordinates: null,
          message: error.code === 1 ? PERMISSION_DENIED : LOCATION_UNAVAILABLE,
        }),
        { enableHighAccuracy: false, maximumAge: 0, timeout: 10000 },
      )
    } catch {
      unavailable()
    }
  })
}
