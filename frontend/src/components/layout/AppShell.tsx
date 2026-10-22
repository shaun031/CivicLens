import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, LogOut, Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { Brand } from './Brand'
import { Sidebar } from './Sidebar'
import { Modal } from '../common/Modal'
import { NotificationBell } from '../notifications/NotificationBell'
import { FormMessage } from '../common/FormParts'
export function AppShell({
  children,
  toolbar,
  hideNotifications = false,
}: {
  children: ReactNode
  toolbar?: ReactNode
  hideNotifications?: boolean
}) {
  const { user, logout } = useAuth()
  const location = useLocation()
  const [compact, setCompact] = useState(false)
  const [mobile, setMobile] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const account = useRef<HTMLDetailsElement>(null)
  const [accountOpen, setAccountOpen] = useState(false)
  const role = user?.role ?? 'CITIZEN'
  const roleLabel =
    role === 'ADMIN'
      ? 'Administration'
      : role === 'OFFICER'
        ? 'Officer workspace'
        : 'Citizen workspace'
  const initials =
    user?.display_name
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((s) => s[0])
      .join('') || 'CL'
  useEffect(() => {
    function close(event: MouseEvent | KeyboardEvent) {
      if (
        (event instanceof KeyboardEvent && event.key === 'Escape') ||
        (event instanceof MouseEvent && !account.current?.contains(event.target as Node))
      ) {
        if (account.current?.open) {
          account.current.open = false
          if (event instanceof KeyboardEvent && account.current.contains(document.activeElement))
            account.current.querySelector('summary')?.focus()
        }
      }
    }
    document.addEventListener('click', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('click', close)
      document.removeEventListener('keydown', close)
    }
  }, [])
  async function signOut() {
    setBusy(true)
    try {
      await logout()
    } catch {
      setError('Sign-out failed. Your session has not been cleared. Try again.')
      setBusy(false)
    }
  }
  return (
    <div className={`app-shell ${compact ? 'sidebar-compact' : ''}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <Brand compact={compact} />
        </div>
        {!compact && <p className="sidebar-caption">{roleLabel}</p>}
        <Sidebar role={role} compact={compact} />
        <div className="sidebar-bottom">
          {!compact && (
            <p>
              Better places.
              <br />
              <strong>One report at a time.</strong>
            </p>
          )}
          <button
            className="icon-button"
            onClick={() => setCompact(!compact)}
            aria-label={compact ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-expanded={!compact}
          >
            {compact ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
          </button>
        </div>
      </aside>
      <div className="app-workspace">
        <header className="app-topbar">
          <div className="flex min-w-0 items-center gap-3">
            <button
              className="icon-button mobile-navigation-toggle"
              aria-label={role === 'CITIZEN' ? 'Open citizen menu' : 'Open workspace menu'}
              aria-expanded={mobile}
              onClick={() => setMobile(true)}
            >
              <Menu size={21} />
            </button>
            <div>
              <p className="topbar-context">CivicLens / {roleLabel}</p>
              <p className="topbar-title">Your community, connected</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 sm:gap-4">
            {!hideNotifications && <NotificationBell />}
            <details
              className="account-menu"
              ref={account}
              onToggle={(event) => setAccountOpen(event.currentTarget.open)}
            >
              <summary>
                <span className="sr-only">Account menu </span>
                <span className="avatar">{initials}</span>
                <span className="account-name">
                  {user?.display_name}
                  <small>{role.toLowerCase()}</small>
                </span>
                <ChevronDown size={14} aria-hidden="true" />
              </summary>
              {accountOpen && (
                <div className="account-dropdown">
                  <p>{user?.email}</p>
                  <Link
                    to={role === 'CITIZEN' ? '/citizen/profile' : '/profile'}
                    onClick={() => {
                      if (account.current) account.current.open = false
                    }}
                  >
                    Edit profile
                  </Link>
                  <button disabled={busy} onClick={() => void signOut()}>
                    <LogOut size={16} aria-hidden="true" />
                    {busy ? 'Signing out…' : 'Sign out'}
                  </button>
                </div>
              )}
            </details>
          </div>
        </header>
        <main id="main-content" className="workspace-content">
          <FormMessage error={error} />
          {toolbar}
          <div key={location.pathname} className="page-transition space-y-6">
            {children}
          </div>
        </main>
        <footer className="workspace-footer">
          <span>CivicLens · Your community, connected</span>
          <Link to="/">Home</Link>
        </footer>
      </div>
      {mobile && (
        <Modal
          title={role === 'CITIZEN' ? 'Citizen menu' : 'Workspace menu'}
          onClose={() => setMobile(false)}
          drawer
        >
          <Brand />
          <div className="mt-7">
            <Sidebar role={role} onNavigate={() => setMobile(false)} />
          </div>
          <Link to="/" className="mt-5 block p-3 text-sm" onClick={() => setMobile(false)}>
            Back to home
          </Link>
        </Modal>
      )}
    </div>
  )
}
