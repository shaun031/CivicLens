import { Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { AppShell } from './AppShell'
import { Footer } from './Footer'
import { Navbar } from './Navbar'

export function AppLayout() {
  const { user } = useAuth()
  const { pathname } = useLocation()
  if (user && /^(\/admin\/|\/officer\/|\/profile$|\/notifications$)/.test(pathname))
    return (
      <AppShell>
        <Outlet />
      </AppShell>
    )
  return (
    <div className="flex min-h-screen flex-col">
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-2"
        href="#main-content"
      >
        Skip to content
      </a>
      <Navbar />
      <main id="main-content" className="flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  )
}
