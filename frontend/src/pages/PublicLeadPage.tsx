import { ArrowRight, CheckCircle2, Clock3, ShieldCheck } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Logo } from '../components/Logo'

interface FormValues {
  name: string
  phone: string
  description: string
}

const initialValues: FormValues = { name: '', phone: '', description: '' }

export function PublicLeadPage() {
  const [values, setValues] = useState(initialValues)
  const [errors, setErrors] = useState<Partial<Record<keyof FormValues, string>>>({})
  const [requestError, setRequestError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)
  const submissionId = useRef(crypto.randomUUID())

  function change(field: keyof FormValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => ({ ...current, [field]: undefined }))
    setRequestError('')
    submissionId.current = crypto.randomUUID()
  }

  function validate() {
    const next: typeof errors = {}
    if (values.name.trim().length < 2) next.name = 'Укажите имя — минимум 2 символа.'
    if (!/^[+\d][\d\s()\-]{6,}$/.test(values.phone.trim())) next.phone = 'Введите корректный номер телефона.'
    if (values.description.trim().length < 10) next.description = 'Опишите задачу чуть подробнее — минимум 10 символов.'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    setRequestError('')
    try {
      await api.submitLead({
        submission_id: submissionId.current,
        name: values.name.trim(),
        phone: values.phone.trim(),
        description: values.description.trim(),
      })
      setSuccess(true)
      setValues(initialValues)
      submissionId.current = crypto.randomUUID()
    } catch (error) {
      setRequestError(error instanceof ApiError ? error.message : 'Не удалось отправить заявку. Попробуйте ещё раз.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="public-page">
      <header className="public-header">
        <Logo />
        <Link to="/login" className="text-link" aria-label="Вход для команды">
          <span className="text-link-full">Вход для команды</span>
          <span className="text-link-short" aria-hidden="true">Вход</span>
          <ArrowRight size={16} />
        </Link>
      </header>
      <main className="public-main">
        <section className="public-intro" aria-labelledby="page-title">
          <hr className="accent-rule" />
          <h1 id="page-title">Расскажите, что нужно починить.</h1>
          <p className="intro-text">Оставьте контакты и коротко опишите задачу. Менеджер уточнит детали и согласует удобное время.</p>
          <ul className="benefit-list">
            <li><Clock3 aria-hidden="true" /><span><strong>Ответим в рабочее время</strong><small>Обычно связываемся в течение часа</small></span></li>
            <li><ShieldCheck aria-hidden="true" /><span><strong>Без лишних рассылок</strong><small>Контакты нужны только для вашей заявки</small></span></li>
          </ul>
          <div className="service-tools" aria-hidden="true">
            <img src="/assets/service-tools.png" alt="" />
          </div>
        </section>

        <section className="lead-form-panel" aria-labelledby="form-title">
          {success ? (
            <div className="success-state" role="status">
              <CheckCircle2 size={42} aria-hidden="true" />
              <h2>Заявка отправлена</h2>
              <p>Спасибо! Менеджер свяжется с вами, чтобы уточнить детали.</p>
              <button className="button button-secondary" type="button" onClick={() => setSuccess(false)}>Оставить ещё одну</button>
            </div>
          ) : (
            <form onSubmit={submit} noValidate>
              <div className="form-heading visually-hidden">
                <h2 id="form-title">Оставить заявку</h2>
              </div>
              {requestError && <div className="alert alert-error" role="alert">{requestError}</div>}
              <div className="indexed-field indexed-field-name">
                <span className="field-index" aria-hidden="true">01</span>
                <div className="field">
                  <label htmlFor="name">Ваше имя</label>
                  <input id="name" name="name" autoComplete="name" value={values.name} onChange={(e) => change('name', e.target.value)} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? 'name-error' : undefined} placeholder="Например, Анна" />
                  {errors.name && <span className="field-error" id="name-error">{errors.name}</span>}
                </div>
              </div>
              <div className="indexed-field indexed-field-phone">
                <span className="field-index" aria-hidden="true">02</span>
                <div className="field">
                  <label htmlFor="phone">Телефон</label>
                  <input id="phone" name="phone" type="tel" inputMode="tel" autoComplete="tel" value={values.phone} onChange={(e) => change('phone', e.target.value)} aria-invalid={Boolean(errors.phone)} aria-describedby={errors.phone ? 'phone-error' : 'phone-help'} placeholder="+7 999 123-45-67" />
                  {errors.phone ? <span className="field-error" id="phone-error">{errors.phone}</span> : <span className="field-help" id="phone-help">Для связи по этой заявке</span>}
                </div>
              </div>
              <div className="indexed-field indexed-field-description">
                <span className="field-index" aria-hidden="true">03</span>
                <div className="field">
                  <label htmlFor="description">Что случилось</label>
                  <textarea id="description" name="description" value={values.description} onChange={(e) => change('description', e.target.value)} aria-invalid={Boolean(errors.description)} aria-describedby={errors.description ? 'description-error' : 'description-help'} placeholder="Например: стиральная машина не сливает воду…" maxLength={2000} />
                  {errors.description ? <span className="field-error" id="description-error">{errors.description}</span> : <span className="field-help" id="description-help">До 2000 символов</span>}
                </div>
              </div>
              <div className="form-actions">
                <button className="button button-primary button-full" type="submit" disabled={submitting}>
                  {submitting ? <><span className="button-loader" aria-hidden="true" />Отправляем…</> : <>Отправить заявку <ArrowRight size={19} /></>}
                </button>
                <p className="privacy-note">Нажимая кнопку, вы соглашаетесь на обработку данных для связи по заявке.</p>
              </div>
            </form>
          )}
        </section>
      </main>
      <footer className="public-footer"><span>© {new Date().getFullYear()} LeadFlow</span><span>Приём заявок на ремонт</span></footer>
    </div>
  )
}
