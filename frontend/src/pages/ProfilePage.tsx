import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { Card, PageHeader } from '../components/common/UI'
import { Button } from '../components/common/Button'
import { Field, FormMessage } from '../components/common/FormParts'

export function ProfilePage() {
  const { user, updateProfile, logout } = useAuth()
  const [name, setName] = useState(user?.display_name ?? '')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setSuccess(null)
    if (name.trim().length < 2) {
      setError('Enter a display name of at least 2 characters.')
      return
    }
    setBusy(true)
    try {
      await updateProfile(name.trim())
      setSuccess('Profile updated.')
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Profile update failed.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <PageHeader
        title="Your profile"
        description="Manage your account details and display name."
      />
      <Card className="max-w-2xl">
        <p className="mb-4 text-sm text-slate-600">
          Real authenticated account information, even when sample preview is enabled.
        </p>
        <dl className="mb-6 space-y-2 text-sm">
          <div>
            <dt className="text-slate-500">Email</dt>
            <dd>{user?.email}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Role</dt>
            <dd>{user?.role}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Account status</dt>
            <dd>{user?.is_active ? 'Active' : 'Inactive'}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Email verification</dt>
            <dd>
              {user?.is_verified ? 'Verified' : 'Not verified'}
              {user?.provider === 'local' ? ' (development-only verification)' : ''}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Authentication provider</dt>
            <dd>{user?.provider}</dd>
          </div>
        </dl>
        <form className="space-y-4" onSubmit={submit}>
          <FormMessage error={error} success={success} />
          <Field
            label="Display name"
            id="display_name"
            required
            minLength={2}
            maxLength={100}
            autoComplete="name"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button type="submit" disabled={busy}>
            Save profile
          </Button>
        </form>
        <button
          className="mt-6 text-sm font-semibold text-teal-700"
          onClick={() => {
            void logout().catch((reason: unknown) =>
              setError(reason instanceof Error ? reason.message : 'Sign-out failed.'),
            )
          }}
        >
          Sign out
        </button>
      </Card>
    </>
  )
}
