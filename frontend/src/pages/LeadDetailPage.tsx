import { ArrowLeft, CalendarDays, Phone, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ManagerShell } from '../components/ManagerShell'
import { LeadExtractionSection } from '../components/LeadExtractionSection'
import { PageLoader } from '../components/PageLoader'
import { StatusBadge, statusLabels } from '../components/StatusBadge'
import { formatHistoryEvent } from '../history'
import type { LeadDetail, LeadExtractionUpdate, LeadStatus } from '../types'

const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export function LeadDetailPage() {
  const { id = '' } = useParams()
  const [lead, setLead] = useState<LeadDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [extractionRefreshError, setExtractionRefreshError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    api.lead(id, controller.signal)
      .then(setLead)
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setError(caught instanceof ApiError ? caught.message : 'Не удалось загрузить заявку.')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id])

  useEffect(() => {
    if (lead?.extraction.status !== 'pending' && lead?.extraction.status !== 'processing') return
    const controller = new AbortController()
    let timeout = window.setTimeout(poll, 1600)

    async function poll() {
      try {
        const updated = await api.lead(id, controller.signal)
        if (controller.signal.aborted) return
        setExtractionRefreshError('')
        setLead((current) => current ? { ...current, extraction: updated.extraction } : current)
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        if (!controller.signal.aborted) setExtractionRefreshError('Связь прервалась. Обновление продолжится автоматически.')
      } finally {
        if (!controller.signal.aborted) timeout = window.setTimeout(poll, 2200)
      }
    }

    return () => {
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [id, lead?.extraction.status])

  async function updateStatus(status: LeadStatus) {
    if (!lead || status === lead.status) return
    const previous = lead
    setLead({ ...lead, status })
    setSaving(true)
    setSaveError('')
    try {
      const updated = await api.updateStatus(id, status)
      setLead((current) => current ? {
        ...current,
        status: updated.status,
        updated_at: updated.updated_at,
        history: updated.history,
      } : current)
    } catch (caught) {
      setLead((current) => current ? { ...current, status: previous.status } : current)
      setSaveError(caught instanceof ApiError ? caught.message : 'Не удалось изменить статус.')
    } finally {
      setSaving(false)
    }
  }

  async function updateExtraction(update: LeadExtractionUpdate) {
    const extraction = await api.updateExtraction(id, update)
    setLead((current) => current ? { ...current, extraction } : current)
    setExtractionRefreshError('')
    return extraction
  }

  async function retryExtraction() {
    const extraction = await api.retryExtraction(id)
    setLead((current) => current ? { ...current, extraction } : current)
    setExtractionRefreshError('')
    return extraction
  }

  async function reloadExtraction() {
    const updated = await api.lead(id)
    setLead((current) => current ? { ...current, extraction: updated.extraction } : current)
    setExtractionRefreshError('')
    return updated.extraction
  }

  if (loading) return <ManagerShell><PageLoader label="Загружаем заявку…" /></ManagerShell>

  return (
    <ManagerShell>
      <main className="manager-main detail-main">
        <Link to="/manager" className="back-link"><ArrowLeft size={17} />К списку заявок</Link>
        {error || !lead ? (
          <div className="content-state error-state" role="alert"><h1>Заявка не открылась</h1><p>{error || 'Заявка не найдена.'}</p></div>
        ) : (
          <>
            <hr className="accent-rule manager-accent" />
            <div className="detail-heading">
              <div><p className="lead-id">Заявка №{lead.id}</p><h1>{lead.name}</h1></div>
              <StatusBadge status={lead.status} />
            </div>
            <div className="detail-layout">
              <div className="detail-content">
                <section className="detail-section" aria-labelledby="description-title">
                  <h2 id="description-title">Описание задачи</h2>
                  <p className="lead-description">{lead.description}</p>
                </section>
                <LeadExtractionSection extraction={lead.extraction} refreshError={extractionRefreshError} onSave={updateExtraction} onRetry={retryExtraction} onReload={reloadExtraction} />
                <section className="detail-section" aria-labelledby="history-title">
                  <h2 id="history-title">История</h2>
                  {lead.history.length ? (
                    <ol className="history-list">
                      {[...lead.history].reverse().map((event) => (
                        <li key={event.id}><span className="history-dot" aria-hidden="true" /><div><p>{formatHistoryEvent(event)}</p><time dateTime={event.created_at}>{dateFormat.format(new Date(event.created_at))}</time></div></li>
                      ))}
                    </ol>
                  ) : <p className="muted-text">Изменений пока не было.</p>}
                </section>
              </div>
              <aside className="detail-sidebar" aria-label="Данные и статус заявки">
                <div className="status-editor">
                  <label htmlFor="detail-status">Статус заявки</label>
                  <select id="detail-status" value={lead.status} disabled={saving} onChange={(e) => updateStatus(e.target.value as LeadStatus)}>
                    {(Object.entries(statusLabels) as [LeadStatus, string][]).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                  </select>
                  <span className="save-caption" aria-live="polite">{saving ? 'Сохраняем…' : 'Изменения сохраняются сразу'}</span>
                  {saveError && <div className="alert alert-error compact" role="alert">{saveError}</div>}
                </div>
                <dl className="lead-meta">
                  <div><dt><UserRound size={17} aria-hidden="true" />Клиент</dt><dd>{lead.name}</dd></div>
                  <div><dt><Phone size={17} aria-hidden="true" />Телефон</dt><dd><a href={`tel:${lead.phone.replace(/[^+\d]/g, '')}`}>{lead.phone}</a></dd></div>
                  <div><dt><CalendarDays size={17} aria-hidden="true" />Создана</dt><dd><time dateTime={lead.created_at}>{dateFormat.format(new Date(lead.created_at))}</time></dd></div>
                </dl>
              </aside>
            </div>
          </>
        )}
      </main>
    </ManagerShell>
  )
}
