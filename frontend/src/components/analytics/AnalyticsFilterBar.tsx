import { useState } from 'react'
import type { FormEvent } from 'react'
import { categories } from '../../types/complaint'
import type { AnalyticsConfig } from '../../services/analyticsService'
import { fieldClass } from '../common/FormParts'
import { Button } from '../common/Button'

export function AnalyticsFilterBar({
  query,
  config,
  onApply,
  geographic = false,
  geographicDefaults = true,
  officers = false,
}: {
  query: URLSearchParams
  config?: AnalyticsConfig
  onApply: (value: URLSearchParams) => void
  geographic?: boolean
  geographicDefaults?: boolean
  officers?: boolean
}) {
  const [preset, setPreset] = useState(query.has('start') ? 'custom' : '30')
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const next = new URLSearchParams()
    for (const [key, value] of form.entries())
      if (typeof value === 'string' && value) next.set(key, value)
    if (preset !== 'custom') {
      const zone = config?.reportingTimezone ?? 'UTC'
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: zone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(new Date())
      const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
      const end = `${get('year')}-${get('month')}-${get('day')}`
      const start = new Date(end + 'T00:00:00Z')
      if (preset === 'month') start.setUTCDate(1)
      else start.setUTCDate(start.getUTCDate() - Number(preset) + 1)
      next.set('start', start.toISOString().slice(0, 10))
      next.set('end', end)
    }
    onApply(next)
  }
  const input = (name: string, label: string, type = 'text', fallback = '') => (
    <label className="block text-sm font-medium" key={name}>
      {label}
      <input
        className={fieldClass}
        name={name}
        type={type}
        step={type === 'number' ? 'any' : undefined}
        defaultValue={query.get(name) ?? fallback}
      />
    </label>
  )
  const select = (name: string, label: string, values: [string, string][]) => (
    <label className="block text-sm font-medium" key={name}>
      {label}
      <select
        className={fieldClass}
        name={name}
        defaultValue={
          query.get(name) ?? (name === 'grouping' ? 'daily' : name === 'grid' ? '0.01' : '')
        }
      >
        {name !== 'grouping' && name !== 'grid' && <option value="">All</option>}
        {values.map(([value, text]) => (
          <option key={value} value={value}>
            {text}
          </option>
        ))}
      </select>
    </label>
  )
  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-slate-200 bg-white p-5"
      aria-label="Analytics filters"
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm font-medium">
          Date preset
          <select className={fieldClass} value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="7">Last 7 days</option>
            <option value="30">Last 30 days</option>
            <option value="90">Last 90 days</option>
            <option value="month">This month</option>
            <option value="custom">Custom range</option>
          </select>
        </label>
        {select('category', 'Infrastructure category', Object.entries(categories))}
        {select('department', 'Department', config?.departments.map((d) => [d.id, d.name]) ?? [])}
        {select(
          'priority',
          'Priority band',
          ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'UNAVAILABLE'].map((v) => [v, v]),
        )}
      </div>
      {preset === 'custom' && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {input('start', 'Start day (inclusive)', 'date')}
          {input('end', 'End day (inclusive)', 'date')}
        </div>
      )}
      <details
        className="mt-4"
        open={
          geographic ||
          officers ||
          ['status', 'assignment', 'urgent', 'area', 'grouping'].some((k) => query.has(k))
        }
      >
        <summary className="text-xs font-semibold text-teal-700">More analytics filters</summary>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {select('status', 'Incident lifecycle', [
            ['OPEN', 'Active'],
            ['RESOLVED', 'Recorded resolved state'],
          ])}
          {select(
            'assignment',
            'Assignment state',
            [
              'UNASSIGNED',
              'DEPARTMENT_ASSIGNED',
              'OFFICER_ASSIGNED',
              'IN_PROGRESS',
              'NEEDS_REVIEW',
            ].map((v) => [v, v.replaceAll('_', ' ')]),
          )}
          {select('urgent', 'Verified hazard', [
            ['true', 'Verified'],
            ['false', 'Not verified'],
          ])}
          {select(
            'area',
            'Configured service area',
            Object.keys(config?.serviceAreas ?? {}).map((v) => [v, v]),
          )}
          {select('grouping', 'Reporting buckets', [
            ['daily', 'Daily'],
            ['weekly', 'Weekly (Monday)'],
            ['monthly', 'Monthly'],
          ])}
          {officers && (
            <>
              {select(
                'availability',
                'Officer availability',
                ['AVAILABLE', 'BUSY', 'UNAVAILABLE', 'ON_LEAVE'].map((v) => [v, v]),
              )}
              {input('minWorkload', 'Minimum global workload', 'number')}
              {input('maxWorkload', 'Maximum global workload', 'number')}
            </>
          )}
          {geographic && (
            <>
              {input('south', 'South latitude', 'number', geographicDefaults ? '12.9' : '')}
              {input('west', 'West longitude', 'number', geographicDefaults ? '77.5' : '')}
              {input('north', 'North latitude', 'number', geographicDefaults ? '13' : '')}
              {input('east', 'East longitude', 'number', geographicDefaults ? '77.7' : '')}
              {select('grid', 'Grid resolution (degrees)', [
                ['0.001', '0.001°'],
                ['0.005', '0.005°'],
                ['0.01', '0.01°'],
                ['0.05', '0.05°'],
                ['0.1', '0.1°'],
              ])}
            </>
          )}
        </div>
      </details>
      <p className="my-4 text-xs text-slate-600">
        Days use the configured municipality zone ({config?.reportingTimezone ?? 'UTC'}), not
        browser midnight. Maximum 366 days. Custom dates require the Custom range preset. Geography
        is a rectangular viewport, not a population-risk model.
        {geographic &&
          !geographicDefaults &&
          ' Leave all four bounds blank for the selected municipality cohort (bounded by server limits).'}
      </p>
      <div className="flex flex-wrap gap-3">
        <Button type="submit">Apply analytics filters</Button>
        <Button type="button" variant="secondary" onClick={() => onApply(new URLSearchParams())}>
          Reset filters
        </Button>
      </div>
    </form>
  )
}
