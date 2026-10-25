import { describe, expect, it } from 'vitest'
import { formatHistoryEvent } from './history'
import type { LeadEvent } from './types'

function event(type: string, message: string): LeadEvent {
  return { id: 'event-id', type, message, created_at: '2026-10-24T14:00:00Z' }
}

describe('history event localization', () => {
  it('localizes lead creation', () => {
    expect(formatHistoryEvent(event('created', 'Lead submitted'))).toBe('Заявка создана')
  })

  it('localizes status names in a status transition', () => {
    expect(formatHistoryEvent(event('status_changed', 'Status changed from new to in_progress')))
      .toBe('Статус изменён: «Новая» → «В работе»')
    expect(formatHistoryEvent(event('status_changed', 'Status changed from in_progress to won')))
      .toBe('Статус изменён: «В работе» → «Завершена»')
  })

  it('keeps known event types Russian when the backend message has an unexpected shape', () => {
    expect(formatHistoryEvent(event('status_changed', 'Unexpected payload'))).toBe('Статус заявки изменён')
  })

  it('keeps the backend message for unknown future event types', () => {
    expect(formatHistoryEvent(event('note_added', 'Добавлен комментарий'))).toBe('Добавлен комментарий')
  })
})
