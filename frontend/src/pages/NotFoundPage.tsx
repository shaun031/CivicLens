import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <section className="mx-auto flex max-w-3xl flex-col items-center px-4 py-24 text-center">
      <p className="text-sm font-bold uppercase tracking-widest text-civic-700">404</p>
      <h1 className="mt-4 text-4xl font-bold text-slate-950">Page not found</h1>
      <p className="mt-4 text-slate-600">The page you requested could not be found.</p>
      <Link className="action-link mt-8" to="/">
        Return home
      </Link>
    </section>
  )
}
