export function formatDate(value: string, time = false) {
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return 'Date unavailable'
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    ...(time ? { timeStyle: 'short' as const } : {}),
  }).format(date)
}
