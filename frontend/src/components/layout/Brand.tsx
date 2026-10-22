import { ScanEye } from 'lucide-react'
import { Link } from 'react-router-dom'
export function Brand({ compact = false, light = false }: { compact?: boolean; light?: boolean }) {
  return (
    <Link to="/" className={`brand ${light ? 'brand-light' : ''}`} aria-label="CivicLens home">
      <span className="brand-symbol">
        <ScanEye size={23} strokeWidth={1.8} aria-hidden="true" />
      </span>
      {!compact && (
        <span>
          Civic<span className="brand-accent">Lens</span>
        </span>
      )}
    </Link>
  )
}
