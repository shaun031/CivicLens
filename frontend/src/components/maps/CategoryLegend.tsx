import { categories } from '../../types/complaint'
import { categoryConfig } from './categoryConfig'
export function CategoryLegend() {
  return (
    <details className="category-legend" open>
      <summary>Map legend</summary>
      <ul aria-label="Issue category legend">
        {Object.entries(categoryConfig).map(([category, config]) => (
          <li key={category}>
            <svg
              viewBox="0 0 24 24"
              width="25"
              height="25"
              style={{ background: config.color }}
              fill="none"
              stroke="#0f172a"
              strokeWidth="2"
              aria-hidden="true"
            >
              {config.paths.map((path) => (
                <path d={path} key={path} />
              ))}
            </svg>
            {categories[category as keyof typeof categories]}
          </li>
        ))}
        <li>
          <span className="legend-center" aria-hidden="true">
            ⊕
          </span>
          Search center
        </li>
      </ul>
    </details>
  )
}
