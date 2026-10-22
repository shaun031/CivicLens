import type { Category } from '../../types/complaint'
export const categoryConfig: Record<Category, { color: string; symbol: string; paths: string[] }> =
  {
    POTHOLE: {
      color: '#ea580c',
      symbol: 'Road defect',
      paths: ['M3 16h18M5 16l3-6 3 3 3-4 5 7M7 20h10'],
    },
    DAMAGED_ROAD: {
      color: '#dc2626',
      symbol: 'Road construction',
      paths: ['M4 8h16v6H4zM7 8l4 6M13 8l4 6M6 14v6M18 14v6'],
    },
    BROKEN_STREETLIGHT: {
      color: '#facc15',
      symbol: 'Lightbulb',
      paths: ['M9 18h6M10 21h4M8 13a6 6 0 1 1 8 0l-1 3H9z'],
    },
    GARBAGE: {
      color: '#16a34a',
      symbol: 'Trash bin',
      paths: ['M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7'],
    },
    DRAINAGE: {
      color: '#2563eb',
      symbol: 'Water and drainage',
      paths: ['M12 3s-6 7-6 11a6 6 0 0 0 12 0c0-4-6-11-6-11zM3 22h18'],
    },
    PUBLIC_PROPERTY_DAMAGE: {
      color: '#9333ea',
      symbol: 'Building',
      paths: ['M4 21V5l8-3 8 3v16M2 21h20M9 21v-5h6v5M8 7h1M15 7h1M8 11h1M15 11h1'],
    },
    OTHER: {
      color: '#64748b',
      symbol: 'Location pin',
      paths: ['M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0zM12 7v6M12 16h.01'],
    },
  }
export function markerConfig(category: string) {
  return Object.hasOwn(categoryConfig, category)
    ? categoryConfig[category as Category]
    : categoryConfig.OTHER
}
