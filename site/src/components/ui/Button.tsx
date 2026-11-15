import { type ButtonHTMLAttributes, type ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'destructive'
type Size = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
  href?: string
  external?: boolean
}

const variantClasses: Record<Variant, string> = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600 shadow-sm',
  secondary: 'bg-white text-ink border border-line-strong hover:bg-surface-muted',
  ghost: 'text-ink-soft hover:bg-surface-muted',
  destructive: 'bg-red-600 text-white hover:bg-red-700',
}

const sizeClasses: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-6 py-3.5 text-base',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  children,
  href,
  external,
  className = '',
  ...rest
}: Props) {
  const cls = `inline-flex items-center justify-center gap-2 rounded-control font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500/40 disabled:opacity-50 disabled:pointer-events-none ${variantClasses[variant]} ${sizeClasses[size]} ${className}`
  if (href) {
    return (
      <a
        href={href}
        target={external ? '_blank' : undefined}
        rel={external ? 'noopener noreferrer' : undefined}
        className={cls}
      >
        {children}
      </a>
    )
  }
  return (
    <button className={cls} {...rest}>
      {children}
    </button>
  )
}

