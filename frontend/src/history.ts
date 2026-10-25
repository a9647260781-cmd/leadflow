import { statusLabels } from './components/StatusBadge'
import type { LeadEvent, LeadStatus } from './types'

const statusChangePattern = /^Status changed from (new|in_progress|won|lost) to (new|in_progress|won|lost)$/

export function formatHistoryEvent(event: LeadEvent): string {
  if (event.type === 'created') return 'Заявка создана'

  if (event.type === 'status_changed') {
    const match = statusChangePattern.exec(event.message)
    if (!match) return 'Статус заявки изменён'

    const previous = statusLabels[match[1] as LeadStatus]
    const next = statusLabels[match[2] as LeadStatus]
    return `Статус изменён: «${previous}» → «${next}»`
  }

  return event.message
}
