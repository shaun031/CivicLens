import { useState } from 'react'
import { Eye, EyeOff, ArrowUpRight, ShieldCheck } from 'lucide-react'
import { Brand } from '../layout/Brand'
import type { InputHTMLAttributes, ReactNode } from 'react'

export const fieldClass = 'form-input'

export function Field({
  label,
  id,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  return (
    <label htmlFor={id} className="block text-sm font-medium text-slate-700">
      {label}
      <input id={id} className={fieldClass} {...props} />
    </label>
  )
}

export function PasswordField({
  label = 'Password',
  id = 'password',
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string; id?: string }) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="password-field">
      <Field label={label} id={id} type={visible ? 'text' : 'password'} {...props} />
      <button
        type="button"
        className="password-toggle"
        aria-controls={id}
        aria-pressed={visible}
        onClick={() => setVisible(!visible)}
      >
        {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        <span className="sr-only">
          {visible ? 'Hide' : 'Show'} {label.toLowerCase()}
        </span>
      </button>
    </div>
  )
}

export function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="auth-layout">
      <aside className="auth-story">
        <Brand light />
        <div>
          <p className="eyebrow">A clearer view. A better community.</p>
          <h2>
            Small observations.
            <br />
            Meaningful change.
          </h2>
          <p>
            Report what needs attention, follow its progress, and help care for the places you
            share.
          </p>
          <div className="auth-story-line">
            <span>
              <ShieldCheck size={20} aria-hidden="true" />
            </span>
            <div>
              <strong>Your reports stay private.</strong>
              <small>Only reviewed summaries appear on the public map.</small>
            </div>
            <ArrowUpRight size={20} aria-hidden="true" />
          </div>
        </div>
        <p className="auth-caption">CivicLens · Public infrastructure, connected.</p>
      </aside>
      <div className="auth-form-panel">
        <div className="auth-form-inner">
          <p className="eyebrow">Welcome to CivicLens</p>
          <h1>{title}</h1>
          <p className="auth-description">
            {title === 'Sign in'
              ? 'Pick up where you left off in your community.'
              : title === 'Create an account'
                ? 'A better neighborhood starts with your first report.'
                : 'Manage your account securely.'}
          </p>
          {children}
        </div>
      </div>
    </section>
  )
}

export function FormMessage({
  error,
  success,
}: {
  error?: string | null
  success?: string | null
}) {
  return (
    <>
      {error && (
        <p role="alert" className="feedback-message bg-red-50 text-red-900">
          {error}
        </p>
      )}
      {success && (
        <p role="status" className="feedback-message bg-emerald-50 text-emerald-900">
          {success}
        </p>
      )}
    </>
  )
}
