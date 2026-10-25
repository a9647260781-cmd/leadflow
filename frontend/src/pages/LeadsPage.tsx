import { ChevronLeft, ChevronRight, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ManagerShell } from '../components/ManagerShell'
import { StatusBadge, statusLabels } from '../components/StatusBadge'
import type { LeadsResponse, LeadStatus } from '../types'

const PAGE_SIZE = 20
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export function LeadsPage() {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<LeadsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const timer = window.setTimeout(() => { setSearch(query.trim()); setPage(1) }, 350)
    return () => window.clearTimeout(timer)
  }, [query])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    api.leads({ search, status, page, pageSize: PAGE_SIZE }, controller.signal)
      .then(setData)
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === 'AbortError') return
        setError(caught instanceof ApiError ? caught.message : 'Не удалось загрузить заявки.')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [page, reloadKey, search, status])

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / PAGE_SIZE))

  return (
    <ManagerShell>
      <main className="manager-main">
        <hr className="accent-rule manager-accent" />
        <div className="page-heading-row">
          <div><h1>Заявки</h1><p>Обращения клиентов и текущий статус работы</p></div>
          {data && <span className="total-count">Всего: {data.total}</span>}
        </div>

        <div className="toolbar" role="search">
          <div className="search-field">
            <Search size={18} aria-hidden="true" />
            <label className="visually-hidden" htmlFor="lead-search">Поиск заявок</label>
            <input id="lead-search" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Имя, телефон или описание" />
          </div>
          <div className="filter-field">
            <SlidersHorizontal size={17} aria-hidden="true" />
            <label className="visually-hidden" htmlFor="status-filter">Статус</label>
            <select id="status-filter" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
              <option value="">Все статусы</option>
              {(Object.entries(statusLabels) as [LeadStatus, string][]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>

        {error ? (
          <div className="content-state error-state" role="alert">
            <h2>Заявки не загрузились</h2><p>{error}</p>
            <button className="button button-secondary" type="button" onClick={() => setReloadKey((current) => current + 1)}>Попробовать снова</button>
          </div>
        ) : loading ? (
          <div className="lead-list skeleton-list" aria-label="Загружаем заявки" aria-busy="true">
            {Array.from({ length: 6 }, (_, index) => <div className="skeleton-row" key={index}><span /><span /><span /><span /></div>)}
          </div>
        ) : data?.items.length ? (
          <>
            <div className="lead-table-wrap">
              <table className="lead-table">
                <thead><tr><th>Клиент</th><th>Заявка</th><th>Статус</th><th>Создана</th><th><span className="visually-hidden">Открыть</span></th></tr></thead>
                <tbody>
                  {data.items.map((lead) => (
                    <tr key={lead.id}>
                      <td><strong>{lead.name}</strong><a href={`tel:${lead.phone.replace(/[^+\d]/g, '')}`}>{lead.phone}</a></td>
                      <td><span className="description-cell">{lead.description}</span></td>
                      <td><StatusBadge status={lead.status} /></td>
                      <td><time dateTime={lead.created_at}>{dateFormat.format(new Date(lead.created_at))}</time></td>
                      <td><Link className="row-link" to={`/manager/leads/${lead.id}`} aria-label={`Открыть заявку от ${lead.name}`}><ChevronRight size={19} /></Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <nav className="pagination" aria-label="Страницы заявок">
                <button type="button" onClick={() => setPage((value) => value - 1)} disabled={page === 1} aria-label="Предыдущая страница"><ChevronLeft size={18} /></button>
                <span>Страница {page} из {totalPages}</span>
                <button type="button" onClick={() => setPage((value) => value + 1)} disabled={page >= totalPages} aria-label="Следующая страница"><ChevronRight size={18} /></button>
              </nav>
            )}
          </>
        ) : (
          <div className="content-state">
            <h2>{search || status ? 'Ничего не найдено' : 'Заявок пока нет'}</h2>
            <p>{search || status ? 'Попробуйте изменить запрос или сбросить фильтры.' : 'Новые обращения клиентов появятся здесь.'}</p>
            {(search || status) && <button className="button button-secondary" type="button" onClick={() => { setQuery(''); setSearch(''); setStatus(''); setPage(1) }}>Сбросить фильтры</button>}
          </div>
        )}
      </main>
    </ManagerShell>
  )
}
