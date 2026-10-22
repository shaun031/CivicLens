import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  variant?: 'primary' | 'secondary'
}

export function Button({
  children,
  className = '',
  type = 'button',
  variant = 'primary',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`ui-button ${variant === 'secondary' ? 'ui-button-secondary' : 'ui-button-primary'} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
