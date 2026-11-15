
export default function SectionHeader({
  eyebrow,
  title,
  description,
  align = 'center',
}: { eyebrow?: string; title: string; description?: string; align?: 'center' | 'left' }) {
  const a = align === 'center' ? 'text-center mx-auto' : 'text-left'
  return (
    <div className={`max-w-2xl ${a}`}>
      {eyebrow && (
        <p className="text-xs font-semibold uppercase tracking-wider text-brand-600">{eyebrow}</p>
      )}
      <h2 className="mt-2 text-3xl font-bold tracking-tight text-ink sm:text-4xl">{title}</h2>
      {description && <p className="mt-4 text-base text-ink-soft sm:text-lg">{description}</p>}
    </div>
  )
}
