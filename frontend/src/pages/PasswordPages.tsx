import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authClient, isAwsAuth } from '../auth/authClient'
import { beginCognitoLogin } from '../auth/cognitoAuthClient'
import { Button } from '../components/common/Button'
import { AuthCard, Field, FormMessage, PasswordField } from '../components/common/FormParts'

function CognitoRecovery() {
  const [error, setError] = useState<string | null>(null)
  return (
    <AuthCard title="Account recovery">
      <p className="mb-4 text-sm text-slate-600">
        Open Cognito’s secure sign-in page and choose “Forgot your password?” to complete account
        recovery.
      </p>
      <Button
        onClick={() => {
          void beginCognitoLogin('/').catch((reason: unknown) =>
            setError(reason instanceof Error ? reason.message : 'Unable to open Cognito.'),
          )
        }}
      >
        Open Cognito recovery
      </Button>
      <FormMessage error={error} />
    </AuthCard>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setMessage((await authClient.forgotPassword(email)).message)
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Recovery failed.')
    } finally {
      setBusy(false)
    }
  }
  if (isAwsAuth) return <CognitoRecovery />
  return (
    <AuthCard title="Forgot password">
      <form onSubmit={submit} className="space-y-4">
        <FormMessage error={error} success={message} />
        <p className="text-sm text-slate-600">
          Local development stores reset links in a private outbox. Ask the local project operator
          to retrieve yours. No email is sent.
        </p>
        <Field
          label="Email"
          id="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Button type="submit" disabled={busy}>
          Request reset link
        </Button>
        <p>
          <Link className="text-sm text-teal-700" to="/login">
            Back to sign in
          </Link>
        </p>
      </form>
    </AuthCard>
  )
}

export function ResetPasswordPage() {
  // Capture the fragment once; reset tokens never reach server access logs or referrers.
  const [token] = useState(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
    return value
  })
  useEffect(() => {
    if (token)
      window.history.replaceState({}, '', window.location.pathname + window.location.search)
  }, [token])
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (password.length < 12 || password !== confirm) {
      setError('Use at least 12 characters and matching passwords.')
      return
    }
    setBusy(true)
    try {
      setMessage((await authClient.resetPassword(token, password, confirm)).message)
      setPassword('')
      setConfirm('')
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Password reset failed.')
    } finally {
      setBusy(false)
    }
  }
  if (isAwsAuth) return <CognitoRecovery />
  return (
    <AuthCard title="Reset password">
      <form onSubmit={submit} className="space-y-4">
        <FormMessage error={error} success={message} />
        {!token && (
          <p role="alert" className="text-sm text-red-800">
            Open the reset link supplied by the local project operator.
          </p>
        )}
        <PasswordField
          label="New password"
          autoComplete="new-password"
          required
          maxLength={128}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <PasswordField
          id="confirm_password"
          label="Confirm password"
          autoComplete="new-password"
          required
          maxLength={128}
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
        <Button type="submit" disabled={!token || busy || !!message}>
          Reset password
        </Button>
        <p>
          <Link className="text-sm text-teal-700" to="/login">
            Sign in
          </Link>
        </p>
      </form>
    </AuthCard>
  )
}
