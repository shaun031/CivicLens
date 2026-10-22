import { Menu } from 'lucide-react'
import { useState } from 'react'
import { Brand } from './Brand'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { dashboardFor } from '../../auth/types'
import { NotificationBell } from '../notifications/NotificationBell'

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
    isActive
      ? 'bg-civic-100 text-civic-700'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
  }`

export function Navbar() {
  const { user } = useAuth()
  const [open, setOpen] = useState(false)
  return (
    <header className="border-b border-slate-200 bg-white">
      <nav
        aria-label="Main navigation"
        className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8"
      >
        <Brand />
        <button
          className="rounded-lg p-2 md:hidden"
          aria-label="Toggle navigation"
          aria-expanded={open}
          aria-controls="public-links"
          onClick={() => setOpen(!open)}
        >
          <Menu aria-hidden="true" />
        </button>
        <div
          id="public-links"
          onClick={() => setOpen(false)}
          className={`${open ? 'flex' : 'hidden'} w-full flex-wrap items-center gap-1 md:flex md:w-auto`}
        >
          <NavLink to="/" end className={navClass}>
            Home
          </NavLink>
          {user ? (
            <>
              <NavLink to={dashboardFor(user.role)} className={navClass}>
                Dashboard
              </NavLink>
              <NavLink to="/profile" className={navClass}>
                Profile
              </NavLink>
              <NotificationBell />
            </>
          ) : (
            <>
              <NavLink to="/login" className={navClass}>
                Sign in
              </NavLink>
              <NavLink to="/register" className="action-link ml-2">
                Get started
              </NavLink>
            </>
          )}
        </div>
      </nav>
    </header>
  )
}
