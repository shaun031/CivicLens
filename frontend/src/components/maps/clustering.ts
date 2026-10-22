export function clusterPoints<T>(
  points: { item: T; x: number; y: number }[],
  cellSize = 64,
): T[][] {
  const buckets = new Map<string, T[]>()
  for (const point of points) {
    const key = `${Math.floor(point.x / cellSize)}:${Math.floor(point.y / cellSize)}`
    const bucket = buckets.get(key) ?? []
    bucket.push(point.item)
    buckets.set(key, bucket)
  }
  return [...buckets.values()]
}
