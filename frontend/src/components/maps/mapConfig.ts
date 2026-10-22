// Bengaluru is a viewport default, never an automatically selected complaint location.
export const DEFAULT_MAP_CENTER: [number, number] = [12.9816, 77.6046]
export const wrapLongitude = (longitude: number) => ((((longitude + 180) % 360) + 360) % 360) - 180
