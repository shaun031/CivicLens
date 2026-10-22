import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { finishCognitoLogin } from '../auth/cognitoAuthClient'
import { dashboardFor } from '../auth/types'
import { AuthCard, FormMessage } from '../components/common/FormParts'

export function AuthCallbackPage() {
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const started = useRef(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (started.current) return
    started.current = true
    void finishCognitoLogin()
      .then(async (destination) => {
        const user = await refresh()
        if (user)
          navigate(destination === '/' ? dashboardFor(user.role) : destination, { replace: true })
        else
          setError('Your account could not be verified. It may require citizen group provisioning.')
      })
      .catch(() =>
        setError('Cognito sign-in could not be completed. Return to sign in and try again.'),
      )
  }, [refresh, navigate])
  return (
    <AuthCard title="Completing sign-in">
      <FormMessage error={error} />
      {!error && <p role="status">Verifying your account…</p>}
    </AuthCard>
  )
}
