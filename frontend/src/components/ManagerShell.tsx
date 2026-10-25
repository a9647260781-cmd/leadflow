import { LogOut } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Logo } from './Logo'

export function ManagerShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [leaving, setLeaving] = useState(false)
  const [logoutError, setLogoutError] = useState('')

  async function handleLogout() {
    setLeaving(true)
    setLogoutError('')
    try {
      await logout()
      navigate('/login', { replace: true })
    } catch (error) {
      setLogoutError(error instanceof ApiError ? error.message : 'Не удалось выйти. Проверьте подключение и повторите.')
    } finally {
      setLeaving(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="manager-header">
        <div className="manager-header-inner">
          <Logo manager />
          <div className="manager-account">
            <div className="account-copy">
              <strong>{user?.name}</strong>
              <span>{user?.email}</span>
            </div>
            <button className="icon-button" type="button" onClick={handleLogout} disabled={leaving} aria-label="Выйти из кабинета" title="Выйти">
              <LogOut size={19} />
            </button>
          </div>
        </div>
      </header>
      {logoutError && (
        <div className="logout-error" role="alert">
          <span><strong>Не удалось выйти.</strong> {logoutError}</span>
          <button type="button" onClick={handleLogout} disabled={leaving}>{leaving ? 'Повторяем…' : 'Повторить'}</button>
        </div>
      )}
      {children}
    </div>
  )
}
