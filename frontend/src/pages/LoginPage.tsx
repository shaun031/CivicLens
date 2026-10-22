import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { isAwsAuth } from '../auth/authClient'
import { dashboardFor, safeDestination } from '../auth/types'
import { Button } from '../components/common/Button'
import { AuthCard, Field, FormMessage, PasswordField } from '../components/common/FormParts'

export function LoginPage() {
  const { login, error: restoreError } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const state = location.state as { from?: unknown } | null
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await login(email, password, safeDestination(state?.from))
      if (user)
        navigate(safeDestination(state?.from, dashboardFor(user.role)), {
          replace: true,
        })
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Sign-in failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <AuthCard title="Sign in">
      <form onSubmit={submit} className="space-y-4">
        <FormMessage error={error ?? restoreError} />
        {isAwsAuth ? (
          <p className="text-sm text-slate-600">Continue to Cognito’s secure sign-in page.</p>
        ) : (
          <>
            <Field
              label="Email"
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <PasswordField
              autoComplete="current-password"
              required
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? 'Signing in…' : isAwsAuth ? 'Continue with Cognito' : 'Sign in'}
        </Button>
        <div className="flex flex-wrap gap-4 text-sm text-teal-700">
          <Link to="/forgot-password">Forgot password?</Link>
          <Link to="/register">Create an account</Link>
        </div>
      </form>
    </AuthCard>
  )
}
