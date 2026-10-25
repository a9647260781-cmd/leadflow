import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
import { AuthProvider, useAuth } from './auth'
import type { User } from './types'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      logout: vi.fn(),
    },
  }
})

const manager: User = { id: 1, email: 'manager@example.com', name: 'Менеджер' }
const mockedApi = vi.mocked(api)

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function AuthProbe({ onError }: { onError: (error: unknown) => void }) {
  const { user, logout } = useAuth()
  return (
    <div>
      <output>{user?.email ?? 'anonymous'}</output>
      <button type="button" onClick={() => void logout().catch(onError)}>Выйти</button>
    </div>
  )
}

describe('logout session handling', () => {
  beforeEach(() => {
    mockedApi.me.mockResolvedValue(manager)
  })

  it('keeps the local session when server logout fails so the user can retry', async () => {
    const onError = vi.fn()
    mockedApi.logout.mockRejectedValue(new ApiError('Нет связи', 0))
    render(<AuthProvider><AuthProbe onError={onError} /></AuthProvider>)
    await screen.findByText(manager.email)

    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }))

    await waitFor(() => expect(onError).toHaveBeenCalledTimes(1))
    expect(screen.getByText(manager.email)).toBeTruthy()
  })

  it('clears the local session after confirmed logout', async () => {
    mockedApi.logout.mockResolvedValue(undefined)
    render(<AuthProvider><AuthProbe onError={vi.fn()} /></AuthProvider>)
    await screen.findByText(manager.email)

    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }))

    await screen.findByText('anonymous')
  })

  it('clears the local session when the server says it is already unauthorized', async () => {
    mockedApi.logout.mockRejectedValue(new ApiError('Not authenticated', 401))
    render(<AuthProvider><AuthProbe onError={vi.fn()} /></AuthProvider>)
    await screen.findByText(manager.email)

    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }))

    await screen.findByText('anonymous')
  })

  it('clears the local session when a protected API request returns 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    })))
    render(<AuthProvider><AuthProbe onError={vi.fn()} /></AuthProvider>)
    await screen.findByText(manager.email)

    await expect(api.leads({ search: '', status: '', page: 1, pageSize: 20 })).rejects.toEqual(expect.objectContaining({ status: 401 }))

    await screen.findByText('anonymous')
  })
})
