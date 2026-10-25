import { ArrowLeft, ArrowRight } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api'
import { useAuth } from '../auth'
import { Logo } from '../components/Logo'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const signInAttempt = useRef(false)

  if (user && !signInAttempt.current) return <Navigate to="/manager" replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (!email.trim() || !password) {
      setError('Введите почту и пароль.')
      return
    }
    setSubmitting(true)
    signInAttempt.current = true
    try {
      await login(email.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from?.startsWith('/manager') ? from : '/manager', { replace: true })
    } catch (caught) {
      signInAttempt.current = false
      const message = caught instanceof ApiError ? caught.message : 'Не удалось войти. Попробуйте ещё раз.'
      setError(caught instanceof ApiError && caught.status === 401 ? 'Неверная почта или пароль.' : message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <div className="login-header"><Logo /></div>
      <section className="login-panel" aria-labelledby="login-title">
        <Link to="/" className="back-link"><ArrowLeft size={16} /> К форме заявки</Link>
        <hr className="accent-rule" />
        <div className="login-heading">
          <h1 id="login-title">Вход в кабинет</h1>
          <p>Для сотрудников сервисной службы</p>
        </div>
        <form onSubmit={submit} noValidate>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="field">
            <label htmlFor="email">Рабочая почта</label>
            <input id="email" type="email" autoComplete="email" value={email} onChange={(e) => { setEmail(e.target.value); setError('') }} placeholder="manager@company.ru" />
          </div>
          <div className="field">
            <label htmlFor="password">Пароль</label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => { setPassword(e.target.value); setError('') }} placeholder="Введите пароль" />
          </div>
          <button className="button button-primary button-full" type="submit" disabled={submitting}>
            {submitting ? <><span className="button-loader" aria-hidden="true" />Входим…</> : <>Войти <ArrowRight size={18} /></>}
          </button>
        </form>
      </section>
    </main>
  )
}
