export function valueLabel(value: unknown): string {
  if (value === null || value === undefined) return 'Not available'
  if (typeof value === 'number')
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 3 })
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string') return value
  if (typeof value === 'object' && 'sampleSize' in value) {
    const sample = value as {
      sampleSize: number
      meanHours?: number | null
      medianHours?: number | null
      minimumHours?: number | null
      maximumHours?: number | null
    }
    return `n=${sample.sampleSize}; mean ${valueLabel(sample.meanHours)}h; median ${valueLabel(sample.medianHours)}h; min ${valueLabel(sample.minimumHours)}h; max ${valueLabel(sample.maximumHours)}h`
  }
  if (typeof value === 'object' && 'denominator' in value) {
    const sample = value as {
      rate: number | null
      denominator: number
      pending: number
      unavailable: number
    }
    return `${sample.rate === null ? 'Not available' : (sample.rate * 100).toFixed(1) + '%'}; n=${sample.denominator}; pending ${sample.pending}; unavailable ${sample.unavailable}`
  }
  return JSON.stringify(value)
}
