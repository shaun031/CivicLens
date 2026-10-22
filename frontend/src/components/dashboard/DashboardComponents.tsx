import { Card } from '../common/UI'
export function StatCard({
  title,
  count,
  sample,
}: {
  title: string
  count: number
  sample: boolean
}) {
  return (
    <Card className="stat-card">
      <p className="text-sm text-slate-600">{title}</p>
      <p className="mt-3 text-3xl font-semibold text-slate-950">{count}</p>
      <p className="mt-2 text-xs text-slate-500">
        {sample ? 'Simulated examples only' : 'Your account'}
      </p>
    </Card>
  )
}
