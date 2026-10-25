import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { LeadDetail } from '../types'
import { LeadDetailPage } from './LeadDetailPage'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return { ...actual, api: { ...actual.api, lead: vi.fn(), updateStatus: vi.fn(), updateExtraction: vi.fn(), retryExtraction: vi.fn() } }
})

vi.mock('../components/ManagerShell', () => ({ ManagerShell: ({ children }: { children: ReactNode }) => <>{children}</> }))

const leadId = 'fd16f11e-4bab-4110-9c35-49515d761a2f'

function lead(status: 'processing' | 'succeeded', service: string): LeadDetail {
  return {
    id: leadId,
    name: 'Мария Тестовая',
    phone: '+7 999 123-45-67',
    description: 'Стиральная машина не сливает воду.',
    status: 'new',
    created_at: '2026-10-24T14:00:00Z',
    updated_at: '2026-10-24T14:00:00Z',
    history: [],
    extraction: {
      status,
      service,
      budget_min: null,
      budget_max: null,
      budget_currency: null,
      budget_text: null,
      timeframe: null,
      evidence: { service: 'Стиральная машина', budget: null, timeframe: null },
      error_code: null,
      attempts: 1,
      updated_at: '2026-10-24T14:00:00Z',
      completed_at: status === 'succeeded' ? '2026-10-24T14:00:01Z' : null,
      manually_edited: false,
      revision: 1,
    },
  }
}

const mockedApi = vi.mocked(api)

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={[`/manager/leads/${leadId}`]}>
      <Routes><Route path="/manager/leads/:id" element={<LeadDetailPage />} /></Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('lead extraction polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  it('polls only an active extraction, preserves an unsaved draft and aborts on route teardown', async () => {
    mockedApi.lead.mockResolvedValueOnce(lead('processing', 'Ремонт техники')).mockResolvedValueOnce(lead('processing', 'Ремонт стиральной машины'))

    const view = renderDetail()

    await act(async () => { await Promise.resolve() })
    fireEvent.click(screen.getByRole('button', { name: 'Исправить разбор' }))
    fireEvent.change(screen.getByLabelText('Услуга'), { target: { value: 'Ручная правка' } })

    await act(async () => { await vi.advanceTimersByTimeAsync(1600) })
    expect((screen.getByLabelText('Услуга') as HTMLInputElement).value).toBe('Ручная правка')
    expect(mockedApi.lead).toHaveBeenCalledTimes(2)

    const pollSignal = mockedApi.lead.mock.calls[1][1]
    expect(pollSignal?.aborted).toBe(false)
    view.unmount()
    expect(pollSignal?.aborted).toBe(true)
  })

  it('does not poll a completed extraction', async () => {
    mockedApi.lead.mockResolvedValueOnce(lead('succeeded', 'Ремонт стиральной машины'))
    renderDetail()
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(mockedApi.lead).toHaveBeenCalledTimes(1)
  })

  it('does not let a delayed status success overwrite a newer manual extraction', async () => {
    const initial = lead('succeeded', 'Изначальный разбор')
    const manual = { ...initial.extraction, service: 'Ручная правка', manually_edited: true, revision: 2 }
    const statusRequest = deferred<LeadDetail>()
    mockedApi.lead.mockResolvedValueOnce(initial)
    mockedApi.updateStatus.mockReturnValue(statusRequest.promise)
    mockedApi.updateExtraction.mockResolvedValue(manual)
    renderDetail()
    await act(async () => { await Promise.resolve() })

    fireEvent.change(screen.getByLabelText('Статус заявки'), { target: { value: 'in_progress' } })
    fireEvent.click(screen.getByRole('button', { name: 'Исправить разбор' }))
    fireEvent.change(screen.getByLabelText('Услуга'), { target: { value: 'Ручная правка' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await act(async () => { await Promise.resolve() })
    expect(screen.getByText('Ручная правка')).toBeTruthy()

    await act(async () => statusRequest.resolve({ ...initial, status: 'in_progress' }))
    expect(screen.getByText('Ручная правка')).toBeTruthy()
    expect((screen.getByLabelText('Статус заявки') as HTMLSelectElement).value).toBe('in_progress')
  })

  it('does not let a delayed status rollback overwrite a newer manual extraction', async () => {
    const initial = lead('succeeded', 'Изначальный разбор')
    const manual = { ...initial.extraction, service: 'Ручная правка', manually_edited: true, revision: 2 }
    const statusRequest = deferred<LeadDetail>()
    mockedApi.lead.mockResolvedValueOnce(initial)
    mockedApi.updateStatus.mockReturnValue(statusRequest.promise)
    mockedApi.updateExtraction.mockResolvedValue(manual)
    renderDetail()
    await act(async () => { await Promise.resolve() })

    fireEvent.change(screen.getByLabelText('Статус заявки'), { target: { value: 'in_progress' } })
    fireEvent.click(screen.getByRole('button', { name: 'Исправить разбор' }))
    fireEvent.change(screen.getByLabelText('Услуга'), { target: { value: 'Ручная правка' } })
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }))
    await act(async () => { await Promise.resolve() })

    await act(async () => statusRequest.reject(new Error('status failed')))
    expect(screen.getByText('Ручная правка')).toBeTruthy()
    expect((screen.getByLabelText('Статус заявки') as HTMLSelectElement).value).toBe('new')
  })
})
