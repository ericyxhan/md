export default function Badge({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'brand' | 'success' }) {
  const cls =
    tone === 'brand'
      ? 'bg-brand-50 text-brand-700 border-brand-100'
      : tone === 'success'
      ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
      : 'bg-surface-muted text-muted border-line'
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {children}
    </span>
  )
}
