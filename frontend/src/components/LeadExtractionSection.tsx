import { Check, Clock3, Pencil, RefreshCw, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { ApiError } from '../api'
import type { LeadExtraction, LeadExtractionUpdate } from '../types'

interface LeadExtractionSectionProps {
  extraction: LeadExtraction
  refreshError?: string
  onReload(): Promise<LeadExtraction>
  onRetry(): Promise<LeadExtraction>
  onSave(update: LeadExtractionUpdate): Promise<LeadExtraction>
}

interface ExtractionDraft {
  service: string
  budgetMin: string
  budgetMax: string
  budgetCurrency: string
  budgetText: string
  timeframe: string
}

const numberFormat = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

const stateCopy: Record<LeadExtraction['status'], { label: string; message: string }> = {
  not_requested: { label: 'Нет разбора', message: 'Для этой заявки разбор ещё не запускался.' },
  pending: { label: 'В очереди', message: 'Заявка ожидает автоматического разбора.' },
  processing: { label: 'Разбираем', message: 'Выделяем услугу, бюджет и желаемый срок.' },
  succeeded: { label: 'Готово', message: 'Проверьте результат по цитатам из исходного описания.' },
  failed: { label: 'Не удалось', message: 'Автоматический разбор временно не завершён.' },
  not_configured: { label: 'Не подключено', message: 'Авторазбор не подключён. Данные можно заполнить вручную.' },
}

function textOrNull(value: string) {
  const normalized = value.trim()
  return normalized || null
}

function draftFrom(extraction: LeadExtraction): ExtractionDraft {
  return {
    service: extraction.service ?? '',
    budgetMin: extraction.budget_min?.toString() ?? '',
    budgetMax: extraction.budget_max?.toString() ?? '',
    budgetCurrency: extraction.budget_currency ?? '',
    budgetText: extraction.budget_text ?? '',
    timeframe: extraction.timeframe ?? '',
  }
}

function nullableNumber(value: string) {
  return value.trim() === '' ? null : Number(value)
}

export function formatBudget(extraction: Pick<LeadExtraction, 'budget_min' | 'budget_max' | 'budget_currency' | 'budget_text'>) {
  const { budget_min: min, budget_max: max, budget_currency: currency, budget_text: text } = extraction
  const suffix = currency ? ` ${currency}` : ''
  if (min !== null && max !== null) {
    if (min === max) return `${numberFormat.format(min)}${suffix}`
    return `от ${numberFormat.format(min)} до ${numberFormat.format(max)}${suffix}`
  }
  if (max !== null) return `до ${numberFormat.format(max)}${suffix}`
  if (min !== null) return `от ${numberFormat.format(min)}${suffix}`
  return text?.trim() || 'Не указано'
}

function safeFailureMessage(errorCode: string | null) {
  if (errorCode === 'provider_timeout' || errorCode === 'timeout') return 'Сервис анализа не ответил вовремя.'
  if (errorCode === 'invalid_response') return 'Ответ сервиса не удалось разобрать.'
  return 'Сервис анализа временно недоступен.'
}

function Evidence({ children }: { children: string | null }) {
  if (!children) return <p className="extraction-evidence empty-evidence">Подтверждение в тексте не найдено.</p>
  return <blockquote className="extraction-evidence">«{children}»</blockquote>
}

export function LeadExtractionSection({ extraction, refreshError = '', onReload, onRetry, onSave }: LeadExtractionSectionProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<ExtractionDraft>(() => draftFrom(extraction))
  const [editBase, setEditBase] = useState<LeadExtraction>(extraction)
  const [conflict, setConflict] = useState(false)
  const [freshExtraction, setFreshExtraction] = useState<LeadExtraction | null>(null)
  const [action, setAction] = useState<'saving' | 'retrying' | 'reloading' | null>(null)
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const state = stateCopy[extraction.status]
  const isActive = extraction.status === 'pending' || extraction.status === 'processing'
  const canRetry = extraction.status === 'failed' || extraction.status === 'not_requested' || extraction.status === 'not_configured'
  const hasValues = Boolean(extraction.service || extraction.budget_min !== null || extraction.budget_max !== null || extraction.budget_text || extraction.timeframe)

  const changed = useMemo(() => {
    const current = draftFrom(editBase)
    return Object.keys(current).some((key) => current[key as keyof ExtractionDraft] !== draft[key as keyof ExtractionDraft].trim())
  }, [draft, editBase])

  function beginEditing() {
    setDraft(draftFrom(extraction))
    setEditBase(extraction)
    setConflict(false)
    setFreshExtraction(null)
    setActionError('')
    setActionMessage('')
    setEditing(true)
  }

  function cancelEditing() {
    setDraft(draftFrom(extraction))
    setEditBase(extraction)
    setConflict(false)
    setFreshExtraction(null)
    setActionError('')
    setActionMessage('')
    setEditing(false)
  }

  async function save() {
    const budgetMin = nullableNumber(draft.budgetMin)
    const budgetMax = nullableNumber(draft.budgetMax)
    const currency = draft.budgetCurrency.trim().toUpperCase()

    if ((budgetMin !== null && (!Number.isFinite(budgetMin) || budgetMin < 0)) || (budgetMax !== null && (!Number.isFinite(budgetMax) || budgetMax < 0))) {
      setActionError('Бюджет должен быть положительным числом или нулём.')
      return
    }
    if (budgetMin !== null && budgetMax !== null && budgetMin > budgetMax) {
      setActionError('Минимальный бюджет не может быть больше максимального.')
      return
    }
    if (currency && !/^[A-Z]{3}$/.test(currency)) {
      setActionError('Укажите валюту тремя латинскими буквами, например RUB, или оставьте поле пустым.')
      return
    }

    const service = textOrNull(draft.service)
    const budgetText = textOrNull(draft.budgetText)
    const timeframe = textOrNull(draft.timeframe)
    const serviceChanged = service !== editBase.service
    const budgetChanged = budgetMin !== editBase.budget_min || budgetMax !== editBase.budget_max || (currency || null) !== editBase.budget_currency || budgetText !== editBase.budget_text
    const timeframeChanged = timeframe !== editBase.timeframe

    setAction('saving')
    setActionError('')
    setActionMessage('')
    try {
      await onSave({
        expected_revision: editBase.revision,
        service,
        budget_min: budgetMin,
        budget_max: budgetMax,
        budget_currency: currency || null,
        budget_text: budgetText,
        timeframe,
        evidence: {
          service: serviceChanged ? null : editBase.evidence.service,
          budget: budgetChanged ? null : editBase.evidence.budget,
          timeframe: timeframeChanged ? null : editBase.evidence.timeframe,
        },
      })
      setEditing(false)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setConflict(true)
        setFreshExtraction(null)
      } else {
        setActionError(caught instanceof ApiError ? caught.message : 'Не удалось сохранить разбор. Попробуйте ещё раз.')
      }
    } finally {
      setAction(null)
    }
  }

  async function reloadAfterConflict() {
    setAction('reloading')
    setActionError('')
    try {
      setFreshExtraction(await onReload())
    } catch (caught) {
      setActionError(caught instanceof ApiError ? caught.message : 'Не удалось загрузить свежую версию. Попробуйте ещё раз.')
    } finally {
      setAction(null)
    }
  }

  function keepDraft() {
    if (!freshExtraction) return
    setEditBase(freshExtraction)
    setConflict(false)
    setFreshExtraction(null)
    setActionMessage('Свежая версия учтена. Проверьте черновик и сохраните ещё раз.')
  }

  function useFreshVersion() {
    if (!freshExtraction) return
    setDraft(draftFrom(freshExtraction))
    setEditBase(freshExtraction)
    setConflict(false)
    setFreshExtraction(null)
    setActionMessage('Форма обновлена свежими данными.')
  }

  async function retry() {
    setAction('retrying')
    setActionError('')
    setActionMessage('')
    try {
      await onRetry()
    } catch (caught) {
      if (extraction.status === 'not_configured' && caught instanceof ApiError && (caught.status === 409 || caught.status === 503)) {
        setActionError('Авторазбор пока не подключён. Настройте сервер и повторите проверку.')
      } else {
        setActionError(caught instanceof ApiError ? caught.message : 'Не удалось запустить разбор. Попробуйте ещё раз.')
      }
    } finally {
      setAction(null)
    }
  }

  return (
    <section className="detail-section extraction-section" aria-labelledby="extraction-title">
      <div className="extraction-heading">
        <div>
          <h2 id="extraction-title">Разбор заявки</h2>
          <p>Подсказка для менеджера — сверьте её с исходным описанием.</p>
        </div>
        <span className={`extraction-state extraction-state-${extraction.status}`} aria-live="polite">
          {isActive && <span className="extraction-spinner" aria-hidden="true" />}
          {extraction.manually_edited && extraction.status === 'succeeded' ? 'Сохранено вручную' : state.label}
        </span>
      </div>

      {editing ? (
        <div className="extraction-form">
          <div className="field compact-field">
            <label htmlFor="extraction-service">Услуга</label>
            <input id="extraction-service" value={draft.service} onChange={(event) => setDraft({ ...draft, service: event.target.value })} placeholder="Не указано" />
          </div>
          <fieldset className="budget-fields">
            <legend>Бюджет</legend>
            <div className="budget-field-grid">
              <div className="field compact-field"><label htmlFor="budget-min">От</label><input id="budget-min" inputMode="decimal" type="number" min="0" step="any" value={draft.budgetMin} onChange={(event) => setDraft({ ...draft, budgetMin: event.target.value })} placeholder="Не указано" /></div>
              <div className="field compact-field"><label htmlFor="budget-max">До</label><input id="budget-max" inputMode="decimal" type="number" min="0" step="any" value={draft.budgetMax} onChange={(event) => setDraft({ ...draft, budgetMax: event.target.value })} placeholder="Не указано" /></div>
              <div className="field compact-field currency-field"><label htmlFor="budget-currency">Валюта</label><input id="budget-currency" value={draft.budgetCurrency} onChange={(event) => setDraft({ ...draft, budgetCurrency: event.target.value.toUpperCase() })} maxLength={3} autoCapitalize="characters" placeholder="Не указано" /></div>
            </div>
            <div className="field compact-field"><label htmlFor="budget-text">Как указано клиентом</label><input id="budget-text" value={draft.budgetText} onChange={(event) => setDraft({ ...draft, budgetText: event.target.value })} placeholder="Не указано" /></div>
            <p className="field-note">Валюту добавляйте только когда она известна.</p>
          </fieldset>
          <div className="field compact-field">
            <label htmlFor="extraction-timeframe">Желаемый срок</label>
            <input id="extraction-timeframe" value={draft.timeframe} onChange={(event) => setDraft({ ...draft, timeframe: event.target.value })} placeholder="Не указано" />
          </div>
          <p className="manual-protection-note">После сохранения фоновый авторазбор не перезапишет ручные правки.</p>
          {conflict && (
            <div className="extraction-conflict" role="alert">
              <strong>Разбор уже изменился</strong>
              <p>Ваш черновик сохранён. Сверьте его со свежей версией, прежде чем сохранять снова.</p>
              {freshExtraction ? (
                <>
                  <dl className="conflict-values">
                    <div><dt>Услуга</dt><dd>{freshExtraction.service || 'Не указано'}</dd></div>
                    <div><dt>Бюджет</dt><dd>{formatBudget(freshExtraction)}</dd></div>
                    <div><dt>Срок</dt><dd>{freshExtraction.timeframe || 'Не указано'}</dd></div>
                  </dl>
                  <div className="conflict-actions">
                    <button type="button" onClick={keepDraft}>Оставить мои правки</button>
                    <button type="button" onClick={useFreshVersion}>Взять свежие данные</button>
                  </div>
                </>
              ) : (
                <button className="button button-secondary conflict-reload" type="button" onClick={reloadAfterConflict} disabled={action === 'reloading'}>
                  {action === 'reloading' ? <span className="button-loader" aria-hidden="true" /> : <RefreshCw size={17} aria-hidden="true" />}
                  {action === 'reloading' ? 'Загружаем…' : 'Загрузить свежую версию'}
                </button>
              )}
            </div>
          )}
          {actionMessage && <p className="extraction-action-note" role="status">{actionMessage}</p>}
          {actionError && <div className="alert alert-error compact extraction-alert" role="alert">{actionError}</div>}
          <div className="extraction-actions">
            <button className="button button-primary" type="button" onClick={save} disabled={action === 'saving' || conflict || !changed}>
              {action === 'saving' ? <span className="button-loader" aria-hidden="true" /> : <Check size={17} aria-hidden="true" />}
              {action === 'saving' ? 'Сохраняем…' : 'Сохранить'}
            </button>
            <button className="button button-secondary" type="button" onClick={cancelEditing} disabled={action === 'saving'}><X size={17} aria-hidden="true" />Отмена</button>
          </div>
        </div>
      ) : (
        <>
          <div className={`extraction-notice extraction-notice-${extraction.status}`} role={extraction.status === 'failed' ? 'alert' : 'status'}>
            <Clock3 size={18} aria-hidden="true" />
            <div><strong>{state.message}</strong>{extraction.status === 'failed' && <span>{safeFailureMessage(extraction.error_code)}</span>}</div>
          </div>
          {refreshError && <p className="extraction-refresh-error" role="status">{refreshError}</p>}

          {(extraction.status === 'succeeded' || hasValues) && (
            <dl className="extraction-values">
              <div><dt>Услуга</dt><dd>{extraction.service || 'Не указано'}</dd><Evidence>{extraction.evidence.service}</Evidence></div>
              <div><dt>Бюджет</dt><dd>{formatBudget(extraction)}</dd><Evidence>{extraction.evidence.budget}</Evidence></div>
              <div><dt>Желаемый срок</dt><dd>{extraction.timeframe || 'Не указано'}</dd><Evidence>{extraction.evidence.timeframe}</Evidence></div>
            </dl>
          )}

          {isActive && hasValues && <p className="previous-values-note">Пока идёт повторный разбор, показаны сохранённые ранее значения.</p>}
          {extraction.manually_edited && extraction.status === 'succeeded' && <p className="manual-protection-note">Ручные правки защищены от фонового авторазбора.</p>}
          {actionError && <div className="alert alert-error compact extraction-alert" role="alert">{actionError}</div>}
          <div className="extraction-actions">
            <button className="button button-secondary" type="button" onClick={beginEditing} disabled={action !== null}>
              <Pencil size={17} aria-hidden="true" />{hasValues ? 'Исправить разбор' : 'Заполнить вручную'}
            </button>
            {canRetry && (
              <button className="button button-secondary" type="button" onClick={retry} disabled={action !== null}>
                {action === 'retrying' ? <span className="button-loader" aria-hidden="true" /> : <RefreshCw size={17} aria-hidden="true" />}
                {action === 'retrying' ? 'Проверяем…' : extraction.status === 'failed' ? 'Повторить разбор' : extraction.status === 'not_configured' ? 'Проверить подключение' : 'Запустить разбор'}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
