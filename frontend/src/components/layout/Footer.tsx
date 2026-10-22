import { Link } from 'react-router-dom'
import { Brand } from './Brand'
export function Footer() {
  return (
    <footer className="public-footer">
      <div>
        <Brand />
        <p>Built for the places we share.</p>
      </div>
      <nav aria-label="Footer navigation">
        <Link to="/citizen/report">Report an issue</Link>
      </nav>
      <p className="footer-note">Independent civic reporting · No municipal affiliation.</p>
    </footer>
  )
}
