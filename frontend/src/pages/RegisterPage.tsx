import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authClient, isAwsAuth } from '../auth/authClient'
import { beginCognitoLogin } from '../auth/cognitoAuthClient'
import { Button } from '../components/common/Button'
import { AuthCard, Field, FormMessage, PasswordField } from '../components/common/FormParts'

export function RegisterPage() {
  const [values, setValues] = useState({
    display_name: '',
    email: '',
    password: '',
    confirm_password: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    if (values.password.length < 12 || values.password.length > 128) {
      setError('Use a password of 12–128 characters.')
      return
    }
    if (values.password !== values.confirm_password) {
      setError('Passwords must match.')
      return
    }
    setBusy(true)
    try {
      await authClient.register(values)
      setValues({
        display_name: '',
        email: '',
        password: '',
        confirm_password: '',
      })
      setSuccess('Citizen account created. You can now sign in.')
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'Registration failed.')
    } finally {
      setBusy(false)
    }
  }
  const field = (name: keyof typeof values) => ({
    value: values[name],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setValues({ ...values, [name]: event.target.value }),
  })
  if (isAwsAuth)
    return (
      <AuthCard title="Create an account">
        <p className="mb-4 text-sm text-slate-600">
          Use Cognito’s registration link on the secure sign-in page. Citizen access becomes
          available after trusted group provisioning.
        </p>
        <Button
          onClick={() => {
            void beginCognitoLogin('/citizen/dashboard').catch((reason: unknown) =>
              setError(reason instanceof Error ? reason.message : 'Unable to open Cognito.'),
            )
          }}
        >
          Open Cognito registration
        </Button>
        <FormMessage error={error} />
      </AuthCard>
    )
  return (
    <AuthCard title="Create an account">
      <form className="space-y-4" onSubmit={submit}>
        <FormMessage error={error} success={success} />
        <Field
          label="Display name"
          id="display_name"
          autoComplete="name"
          required
          maxLength={100}
          {...field('display_name')}
        />
        <Field
          label="Email"
          id="email"
          type="email"
          autoComplete="email"
          required
          {...field('email')}
        />
        <PasswordField
          autoComplete="new-password"
          required
          maxLength={128}
          {...field('password')}
        />
        <p className="text-sm text-slate-600">
          Use 12–128 characters. A long, unique passphrase is welcome.
        </p>
        <PasswordField
          label="Confirm password"
          id="confirm_password"
          autoComplete="new-password"
          required
          maxLength={128}
          {...field('confirm_password')}
        />
        <Button type="submit" disabled={busy}>
          {busy ? 'Creating account…' : 'Create citizen account'}
        </Button>
        <p>
          <Link className="text-sm text-teal-700" to="/login">
            Already registered? Sign in
          </Link>
        </p>
      </form>
    </AuthCard>
  )
}
