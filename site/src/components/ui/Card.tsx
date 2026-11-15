import { type ReactNode } from 'react'

export default function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-card border border-line bg-surface p-6 shadow-[0_1px_2px_rgba(14,27,37,0.04)] ${className}`}>
      {children}
    </div>
  )
}
