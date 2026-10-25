import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { api, ApiError, onUnauthorized } from './api'
import type { User } from './types'
import { PageLoader } from './components/PageLoader'

interface AuthValue {
  user: User | null
  loading: boolean
  login(email: string, password: string): Promise<void>
  logout(): Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    const unsubscribe = onUnauthorized(() => setUser(null))

    api.me(controller.signal)
      .then(setUser)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        if (!(error instanceof ApiError && error.status === 401)) console.error(error)
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  const value = useMemo<AuthValue>(() => ({
    user,
    loading,
    async login(email, password) {
      setUser(await api.login(email, password))
    },
    async logout() {
      try {
        await api.logout()
        setUser(null)
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          setUser(null)
          return
        }
        throw error
      }
    },
  }), [loading, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}

export function ProtectedRoute() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <PageLoader label="Проверяем доступ…" />
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />
  return <Outlet />
}
