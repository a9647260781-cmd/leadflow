import { Wrench } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Logo({ manager = false }: { manager?: boolean }) {
  return (
    <Link to={manager ? '/manager' : '/'} className="logo" aria-label="LeadFlow — главная">
      <span className="logo-mark" aria-hidden="true"><Wrench size={17} strokeWidth={2.2} /></span>
      <span>LeadFlow</span>
    </Link>
  )
}
