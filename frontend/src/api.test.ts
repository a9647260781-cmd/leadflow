import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, onUnauthorized } from './api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('API request behavior', () => {
  it('omits an empty status filter so FastAPI does not reject it as an enum', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.leads({ search: '', status: '', page: 1, pageSize: 20 })

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    const params = new URL(url, 'http://localhost').searchParams
    expect(params.has('status')).toBe(false)
    expect(params.get('page')).toBe('1')
    expect(params.get('page_size')).toBe('20')
  })

  it('keeps a non-empty status filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.leads({ search: 'Анна', status: 'in_progress', page: 2, pageSize: 20 })

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    const params = new URL(url, 'http://localhost').searchParams
    expect(params.get('status')).toBe('in_progress')
    expect(params.get('search')).toBe('Анна')
  })

  it('preserves AbortError instead of presenting cancellation as a network failure', async () => {
    const abortError = new DOMException('The operation was aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError))

    await expect(api.leads({ search: '', status: '', page: 1, pageSize: 20 })).rejects.toBe(abortError)
  })

  it('invalidates auth on protected 401 but not on a rejected login', async () => {
    const listener = vi.fn()
    const unsubscribe = onUnauthorized(listener)
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Not authenticated' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    }))))

    await expect(api.leads({ search: '', status: '', page: 1, pageSize: 20 })).rejects.toEqual(expect.objectContaining({ status: 401 }))
    expect(listener).toHaveBeenCalledTimes(1)

    await expect(api.updateExtraction('lead-id', {
      expected_revision: 1, service: null, budget_min: null, budget_max: null, budget_currency: null, budget_text: null,
      timeframe: null, evidence: { service: null, budget: null, timeframe: null },
    })).rejects.toEqual(expect.objectContaining({ status: 401 }))
    expect(listener).toHaveBeenCalledTimes(2)

    await expect(api.login('wrong@example.com', 'wrong')).rejects.toBeInstanceOf(ApiError)
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
  })

  it('sends manual extraction replacements and retry requests only to protected same-origin endpoints', async () => {
    const response = {
      status: 'succeeded', service: null, budget_min: null, budget_max: null, budget_currency: null, budget_text: null,
      timeframe: null, evidence: { service: null, budget: null, timeframe: null }, error_code: null, attempts: 1,
      updated_at: '2026-10-24T14:00:00Z', completed_at: '2026-10-24T14:00:00Z', manually_edited: true, revision: 2,
    }
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(response), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    vi.stubGlobal('fetch', fetchMock)

    const replacement = { expected_revision: 7, service: null, budget_min: null, budget_max: null, budget_currency: null, budget_text: null, timeframe: null, evidence: { service: null, budget: null, timeframe: null } }
    await api.updateExtraction('lead/id', replacement)
    await api.retryExtraction('lead/id')

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/leads/lead%2Fid/extraction', expect.objectContaining({ method: 'PATCH', credentials: 'include', body: JSON.stringify(replacement) }))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/leads/lead%2Fid/extraction/retry', expect.objectContaining({ method: 'POST', credentials: 'include', body: JSON.stringify({ overwrite_manual: false }) }))
  })
})
