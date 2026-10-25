import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
import App from './App'
import type { LeadDetail, User } from './types'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      login: vi.fn(),
      lead: vi.fn(),
    },
  }
})

const manager: User = { id: 'manager-id', email: 'manager@example.com', name: 'Менеджер' }
const leadId = 'fd16f11e-4bab-4110-9c35-49515d761a2f'
const lead: LeadDetail = {
  id: leadId,
  name: 'Мария Тестовая',
  phone: '+7 999 123-45-67',
  description: 'Стиральная машина не сливает воду.',
  status: 'new',
  created_at: '2026-10-24T14:00:00Z',
  updated_at: '2026-10-24T14:00:00Z',
  history: [],
  extraction: {
    status: 'not_requested',
    service: null,
    budget_min: null,
    budget_max: null,
    budget_currency: null,
    budget_text: null,
    timeframe: null,
    evidence: { service: null, budget: null, timeframe: null },
    error_code: null,
    attempts: 0,
    updated_at: '2026-10-24T14:00:00Z',
    completed_at: null,
    manually_edited: false,
    revision: 0,
  },
}
const mockedApi = vi.mocked(api)

afterEach(cleanup)

describe('protected route login return path', () => {
  beforeEach(() => {
    mockedApi.me.mockRejectedValue(new ApiError('Not authenticated', 401))
    mockedApi.login.mockResolvedValue(manager)
    mockedApi.lead.mockResolvedValue(lead)
  })

  it('returns a user who opened a protected detail URL to that same lead after login', async () => {
    render(
      <MemoryRouter initialEntries={[`/manager/leads/${leadId}`]}>
        <App />
      </MemoryRouter>,
    )

    await screen.findByRole('heading', { name: 'Вход в кабинет' })
    fireEvent.change(screen.getByLabelText('Рабочая почта'), { target: { value: manager.email } })
    fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'password' } })
    fireEvent.click(screen.getByRole('button', { name: /Войти/ }))

    expect(await screen.findByRole('heading', { name: lead.name })).toBeTruthy()
    expect(mockedApi.lead).toHaveBeenCalledWith(leadId, expect.any(AbortSignal))
  })
})
