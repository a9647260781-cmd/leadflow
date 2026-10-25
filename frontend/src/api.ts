import type { LeadDetail, LeadExtraction, LeadExtractionUpdate, LeadsResponse, LeadStatus, User } from './types'

type UnauthorizedListener = () => void

const unauthorizedListeners = new Set<UnauthorizedListener>()

export function onUnauthorized(listener: UnauthorizedListener) {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

function notifyUnauthorized() {
  unauthorizedListeners.forEach((listener) => listener())
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function errorMessage(body: unknown): string {
  if (!body || typeof body !== 'object' || !('detail' in body)) return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
  const detail = (body as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        return 'msg' in item && typeof item.msg === 'string' ? item.msg : ''
      })
      .filter(Boolean)
      .join('. ') || 'Проверьте заполненные поля.'
  }
  return 'Не удалось выполнить запрос. Попробуйте ещё раз.'
}

interface RequestOptions extends RequestInit {
  invalidateSessionOn401?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response: Response
  const { invalidateSessionOn401 = false, ...fetchOptions } = options
  try {
    response = await fetch(path, {
      ...fetchOptions,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...fetchOptions.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    if (fetchOptions.signal?.aborted) throw error
    throw new ApiError('Нет связи с сервером. Проверьте подключение и повторите.', 0)
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    if (response.status === 401 && invalidateSessionOn401) notifyUnauthorized()
    throw new ApiError(errorMessage(body), response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  submitLead: (data: { submission_id: string; name: string; phone: string; description: string }) =>
    request<{ id: number | string; created_at: string }>('/api/leads', { method: 'POST', body: JSON.stringify(data) }),
  login: (email: string, password: string) =>
    request<User>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  me: (signal?: AbortSignal) => request<User>('/api/auth/me', { signal }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  leads: (params: { search: string; status: string; page: number; pageSize: number }, signal?: AbortSignal) => {
    const query = new URLSearchParams({
      search: params.search,
      page: String(params.page),
      page_size: String(params.pageSize),
    })
    if (params.status) query.set('status', params.status)
    return request<LeadsResponse>(`/api/leads?${query}`, { signal, invalidateSessionOn401: true })
  },
  lead: (id: string, signal?: AbortSignal) => request<LeadDetail>(`/api/leads/${encodeURIComponent(id)}`, { signal, invalidateSessionOn401: true }),
  updateStatus: (id: string, status: LeadStatus) =>
    request<LeadDetail>(`/api/leads/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ status }), invalidateSessionOn401: true }),
  updateExtraction: (id: string, extraction: LeadExtractionUpdate) =>
    request<LeadExtraction>(`/api/leads/${encodeURIComponent(id)}/extraction`, {
      method: 'PATCH',
      body: JSON.stringify(extraction),
      invalidateSessionOn401: true,
    }),
  retryExtraction: (id: string, overwriteManual = false) =>
    request<LeadExtraction>(`/api/leads/${encodeURIComponent(id)}/extraction/retry`, {
      method: 'POST',
      body: JSON.stringify({ overwrite_manual: overwriteManual }),
      invalidateSessionOn401: true,
    }),
}
