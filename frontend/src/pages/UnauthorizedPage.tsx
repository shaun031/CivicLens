import { Link } from 'react-router-dom'
import { AuthCard } from '../components/common/FormParts'

export function UnauthorizedPage() {
  return (
    <AuthCard title="Access denied">
      <p className="text-slate-600">Your account does not have permission to open this page.</p>
      <Link to="/profile" className="mt-5 inline-block text-teal-700">
        View your profile
      </Link>
    </AuthCard>
  )
}
