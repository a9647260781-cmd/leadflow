export function PageLoader({ label }: { label: string }) {
  return (
    <main className="center-page" aria-live="polite" aria-busy="true">
      <span className="loader" aria-hidden="true" />
      <p>{label}</p>
    </main>
  )
}
