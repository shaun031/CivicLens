import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { categories } from '../types/complaint'
import { categoryConfig, markerConfig } from '../components/maps/categoryConfig'
import { categoryMarker } from '../components/maps/markerIcons'
import { clusterPoints } from '../components/maps/clustering'
import { CategoryLegend } from '../components/maps/CategoryLegend'

describe('Category marker registry and bounded visualization clustering', () => {
  it('covers every existing backend category with a local SVG and a unique color', () => {
    expect(Object.keys(categoryConfig).sort()).toEqual(Object.keys(categories).sort())
    expect(new Set(Object.values(categoryConfig).map((config) => config.color)).size).toBe(7)
    for (const category of Object.keys(categories)) {
      const icon = categoryMarker(category)
      expect(icon.options.iconSize).toEqual([36, 36])
      expect(icon.options.html).toContain('<svg')
      expect(icon.options.html).toContain(markerConfig(category).color)
      expect(icon.options.html).not.toMatch(/https?:|<img|script|undefined/)
    }
    expect(categoryMarker('UNKNOWN')).toBe(categoryMarker('OTHER'))
    expect(markerConfig('UNKNOWN')).toBe(categoryConfig.OTHER)
    expect(markerConfig('__proto__')).toBe(categoryConfig.OTHER)
    expect(markerConfig('constructor')).toBe(categoryConfig.OTHER)
  })
  it.each([
    ['POTHOLE', '#ea580c'],
    ['DAMAGED_ROAD', '#dc2626'],
    ['BROKEN_STREETLIGHT', '#facc15'],
    ['GARBAGE', '#16a34a'],
    ['DRAINAGE', '#2563eb'],
    ['PUBLIC_PROPERTY_DAMAGE', '#9333ea'],
    ['OTHER', '#64748b'],
  ])('%s has its specified color and distinct SVG', (category, color) => {
    expect(markerConfig(category).color).toBe(color)
    expect(categoryMarker(category).options.html).toContain(color)
    if (category !== 'POTHOLE')
      expect(categoryMarker(category).options.html).not.toBe(categoryMarker('POTHOLE').options.html)
  })
  it('exposes a collapsible accessible legend with every category and the search center', () => {
    const { container } = render(<CategoryLegend />)
    expect(screen.getByText('Map legend').closest('details')).toHaveAttribute('open')
    expect(screen.getByRole('list', { name: 'Issue category legend' }).children).toHaveLength(8)
    expect(screen.getByText('Search center')).toBeInTheDocument()
    expect(container.querySelectorAll('svg')).toHaveLength(7)
  })
  it('clusters dense pixels without changing records, and separates them after zoom projection', () => {
    const records = [{ id: 1 }, { id: 2 }, { id: 3 }]
    const clustered = clusterPoints(records.map((item, index) => ({ item, x: index * 10, y: 20 })))
    expect(clustered).toEqual([records])
    const zoomed = clusterPoints(records.map((item, index) => ({ item, x: index * 100, y: 20 })))
    expect(zoomed).toEqual(records.map((item) => [item]))
    expect(zoomed[0][0]).toBe(records[0])
    expect(clusterPoints([])).toEqual([])
  })
})
