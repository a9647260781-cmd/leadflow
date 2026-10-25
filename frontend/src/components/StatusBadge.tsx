import type { LeadStatus } from '../types'

export const statusLabels: Record<LeadStatus, string> = {
  new: 'Новая',
  in_progress: 'В работе',
  won: 'Завершена',
  lost: 'Отказ',
}

export function StatusBadge({ status }: { status: LeadStatus }) {
  return <span className={`status status-${status}`}><span aria-hidden="true" />{statusLabels[status]}</span>
}
