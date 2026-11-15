import { type ReactNode } from 'react'

export default function Section({
  children,
  className = '',
  id,
}: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`py-16 sm:py-24 ${className}`}>
      {children}
    </section>
  )
}
