import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LeadExtraction } from '../types'
import { ApiError } from '../api'
import { formatBudget, LeadExtractionSection } from './LeadExtractionSection'

function extraction(overrides: Partial<LeadExtraction> = {}): LeadExtraction {
  return {
    status: 'succeeded',
    service: 'Ремонт стиральной машины',
    budget_min: 3000,
    budget_max: 5000,
    budget_currency: 'RUB',
    budget_text: '3–5 тысяч рублей',
    timeframe: 'На этой неделе',
    evidence: {
      service: 'стиральная машина не сливает воду',
      budget: 'до 5 тысяч рублей',
      timeframe: 'на этой неделе',
    },
    error_code: null,
    attempts: 1,
    updated_at: '2026-10-24T14:00:00Z',
    completed_at: '2026-10-24T14:00:00Z',
    manually_edited: false,
    revision: 1,
    ...overrides,
  }
}

afterEach(cleanup)

describe('lead extraction presentation', () => {
  it('formats exact, range, upper and lower budgets without inventing a currency', () => {
    expect(formatBudget(extraction({ budget_min: 4000, budget_max: 4000, budget_currency: 'RUB' }))).toBe('4 000 RUB')
    expect(formatBudget(extraction({ budget_min: 3000, budget_max: 5000, budget_currency: 'RUB' }))).toBe('от 3 000 до 5 000 RUB')
    expect(formatBudget(extraction({ budget_min: null, budget_max: 5000, budget_currency: null }))).toBe('до 5 000')
    expect(formatBudget(extraction({ budget_min: 3000, budget_max: null, budget_currency: null }))).toBe('от 3 000')
  })

  it('renders unknown values explicitly and keeps provider failure details private', () => {
    const { rerender } = render(<LeadExtractionSection extraction={extraction({ service: null, budget_min: null, budget_max: null, budget_currency: null, budget_text: null, timeframe: null, evidence: { service: null, budget: null, timeframe: null } })} onRetry={vi.fn()} onSave={vi.fn()} onReload={vi.fn()} />)
    expect(screen.getAllByText('Не указано')).toHaveLength(3)

    rerender(<LeadExtractionSection extraction={extraction({ status: 'failed', error_code: 'secret-provider-stack-trace' })} onRetry={vi.fn()} onSave={vi.fn()} onReload={vi.fn()} />)
    expect(screen.getByText('Сервис анализа временно недоступен.')).toBeTruthy()
    expect(screen.queryByText('secret-provider-stack-trace')).toBeNull()
  })

  it('is honest when the provider is not configured and allows a later connection check', async () => {
    const onRetry = vi.fn().mockRejectedValue(new ApiError('Extraction provider is not configured', 409))
    render(<LeadExtractionSection extraction={extraction({ status: 'not_configured', service: null, budget_min: null, budget_max: null, budget_currency: null, budget_text: null, timeframe: null })} onRetry={onRetry} onSave={vi.fn()} onReload={vi.fn()} />)
    expect(screen.getByText('Авторазбор не подключён. Данные можно заполнить вручную.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Заполнить вручную' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Проверить подключение' }))
    expect(await screen.findByText('Авторазбор пока не подключён. Настройте сервер и повторите проверку.')).toBeTruthy()
    expect(screen.queryByText('Extraction provider is not configured')).toBeNull()
  })

  it('saves manual corrections and clears evidence that no longer supports the edited value', async () => {
    const current = extraction()
    const saved = extraction({ service: 'Диагностика стиральной машины', evidence: { ...current.evidence, service: null }, manually_edited: true, revision: 2 })
    const onSave = vi.fn().mockResolvedValue(saved)
    render(<LeadExtractionSection extraction={current} onRetry={vi.fn()} onSave={onSave} onReload={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Исправить разбор' }))
    fireEvent.change(screen.getByLabelText('Услуга'), { target: { value: 'Диагностика стиральной машины' } })
    expect(screen.getByText('После сохранения фоновый авторазбор не перезапишет ручные правки.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      expected_revision: 1,
      service: 'Диагностика стиральной машины',
      evidence: { ...current.evidence, service: null },
    }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Сохранить' })).toBeNull())
  })

  it('retries a failed extraction from an authenticated detail screen', async () => {
    const onRetry = vi.fn().mockResolvedValue(extraction({ status: 'pending' }))
    render(<LeadExtractionSection extraction={extraction({ status: 'failed', error_code: 'provider_timeout' })} onRetry={onRetry} onSave={vi.fn()} onReload={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Повторить разбор' }))
    await waitFor(() => expect(onRetry).toHaveBeenCalledTimes(1))
  })

  it('keeps a stale draft on revision conflict and rebases only after an explicit choice', async () => {
    const original = extraction({ revision: 4 })
    const fresh = extraction({ revision: 5, service: 'Свежий разбор с сервера' })
    const saved = extraction({ revision: 6, service: 'Ручная правка', manually_edited: true })
    const onSave = vi.fn().mockRejectedValueOnce(new ApiError('Extraction was changed; reload before saving', 409)).mockResolvedValueOnce(saved)
    const onReload = vi.fn().mockResolvedValue(fresh)
    render(<LeadExtractionSection extraction={original} onRetry={vi.fn()} onSave={onSave} onReload={onReload} />)

    fireEvent.click(screen.getByRole('button', { name: 'Исправить разбор' }))
    fireEvent.change(screen.getByLabelText('Услуга'), { target: { value: 'Ручная правка' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))

    expect(await screen.findByText('Разбор уже изменился')).toBeTruthy()
    expect((screen.getByLabelText('Услуга') as HTMLInputElement).value).toBe('Ручная правка')
    fireEvent.click(screen.getByRole('button', { name: 'Загрузить свежую версию' }))
    expect(await screen.findByText('Свежий разбор с сервера')).toBeTruthy()
    expect((screen.getByLabelText('Услуга') as HTMLInputElement).value).toBe('Ручная правка')

    fireEvent.click(screen.getByRole('button', { name: 'Оставить мои правки' }))
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2))
    expect(onSave.mock.calls[0][0].expected_revision).toBe(4)
    expect(onSave.mock.calls[1][0]).toEqual(expect.objectContaining({ expected_revision: 5, service: 'Ручная правка' }))
  })
})
