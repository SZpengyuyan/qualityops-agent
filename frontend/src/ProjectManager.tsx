import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage, request } from './api'
import type { Project, ProjectInput, ProjectPage } from './api'
import { OpenAPIManager } from './OpenAPIManager'
import { TestAssets } from './TestAssets'

const emptyProject: ProjectInput = { name: '', description: '', base_url: '' }
const button = 'rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:cursor-wait disabled:opacity-50'
const input = 'mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-2 focus:outline-indigo-200'
const pageSize = 6

export function ProjectManager() {
  const [page, setPage] = useState<ProjectPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Project | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [draft, setDraft] = useState<ProjectInput | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [assetRevision, setAssetRevision] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setListError('')
    request<ProjectPage>(`/api/projects?limit=${pageSize}&offset=${offset}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setPage(result) })
      .catch(error => { if (!controller.signal.aborted) setListError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [offset, revision])

  useEffect(() => {
    setSelected(null)
    if (!selectedId) { setDetailLoading(false); return }
    const controller = new AbortController()
    setDetailLoading(true)
    request<Project>(`/api/projects/${selectedId}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setSelected(result) })
      .catch(error => { if (!controller.signal.aborted) setActionError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [selectedId])

  function refreshList() { setRevision(value => value + 1) }
  function clearPanel() {
    setSelectedId(null); setSelected(null); setDraft(null); setEditingId(null)
    setConfirmDelete(false); setActionError('')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft || busy) return
    setBusy(true); setActionError(''); setNotice('')
    try {
      await request<Project>(editingId ? `/api/projects/${editingId}` : '/api/projects', {
        method: editingId ? 'PUT' : 'POST', body: JSON.stringify(draft),
      })
      setNotice(editingId ? '项目已更新。' : '项目已创建。')
      clearPanel(); setOffset(0); refreshList()
    } catch (error) { setActionError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  async function remove() {
    if (!selected || busy) return
    setBusy(true); setActionError(''); setNotice('')
    try {
      await request<void>(`/api/projects/${selected.id}`, { method: 'DELETE' })
      setNotice('项目已删除。'); clearPanel(); setOffset(0); refreshList()
    } catch (error) { setActionError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  return (
    <section aria-labelledby="projects-title" className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div><h2 id="projects-title" className="text-lg font-semibold">项目管理</h2><p className="mt-1 text-sm text-slate-500">管理待测服务，配置项目名称和 API 基础地址。</p></div>
        <div className="flex gap-2"><button className={button} disabled={busy || loading} onClick={refreshList}>刷新列表</button>
          <button className={`${button} border-indigo-600 bg-indigo-600 text-white hover:bg-indigo-700`} disabled={busy} onClick={() => { clearPanel(); setNotice(''); setDraft({ ...emptyProject }) }}>新建项目</button></div>
      </div>
      {notice && <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
      {listError && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">列表加载失败：{listError}</p>}
      {loading ? <p role="status" className="py-10 text-center text-sm text-slate-500">正在加载项目…</p> : listError ? null : page?.items.length ? (
        <ul className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {page.items.map(project => <li key={project.id} className={`min-w-0 rounded-xl border p-4 ${selectedId === project.id ? 'border-indigo-400 bg-indigo-50/30' : 'border-slate-200'}`}>
            <h3 className="truncate font-semibold" title={project.name}>{project.name}</h3>
            <p className="mt-2 truncate font-mono text-xs text-slate-500" title={project.base_url}>{project.base_url}</p>
            <p className="mt-3 line-clamp-2 min-h-10 break-words text-sm text-slate-500">{project.description || '暂无描述'}</p>
            <button className={`${button} mt-4`} disabled={busy} aria-label={`查看 ${project.name}`} onClick={() => { setDraft(null); setEditingId(null); setConfirmDelete(false); setActionError(''); setSelectedId(project.id); setNotice('') }}>查看项目</button>
          </li>)}
        </ul>
      ) : <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-8 text-center"><p className="font-medium">{offset > 0 ? '这一页暂无项目' : '还没有项目'}</p><p className="mt-2 text-sm text-slate-500">点击“新建项目”，添加第一个待测服务。</p></div>}
      {page && !loading && !listError && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500"><span>共 {page.total} 个项目 · 第 {Math.floor(offset / pageSize) + 1} 页</span><div className="flex gap-2"><button className={button} disabled={busy || offset === 0} onClick={() => setOffset(value => Math.max(0, value - pageSize))}>上一页</button><button className={button} disabled={busy || offset + pageSize >= page.total} onClick={() => setOffset(value => value + pageSize)}>下一页</button></div></div>}

      {actionError && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{actionError}</p>}
      {detailLoading && <p role="status" className="mt-6 text-sm text-slate-500">正在读取项目详情…</p>}
      {selected && !draft && <div className="mt-6 rounded-xl border border-indigo-100 bg-indigo-50/30 p-5">
        <h3 className="break-words font-semibold">{selected.name}</h3><p className="mt-2 break-all font-mono text-xs text-slate-500">{selected.base_url}</p>
        <p className="mt-3 whitespace-pre-wrap break-words text-sm text-slate-600">{selected.description || '暂无描述'}</p>
        <p className="mt-4 break-all text-xs text-slate-400">ID: {selected.id} · 创建于 {new Date(selected.created_at).toLocaleString('zh-CN')}</p>
        <div className="mt-4 flex flex-wrap gap-2"><button disabled={busy} className={button} onClick={() => { setDraft({ name: selected.name, description: selected.description, base_url: selected.base_url }); setEditingId(selected.id); setConfirmDelete(false); setActionError('') }}>编辑项目</button><button disabled={busy} className={`${button} text-rose-700`} onClick={() => setConfirmDelete(true)}>删除项目</button><button disabled={busy} className={button} onClick={clearPanel}>关闭详情</button></div>
        {confirmDelete && <div className="mt-4 rounded-lg border border-rose-200 bg-white p-4"><p className="text-sm text-rose-700">确定删除“{selected.name}”？此操作无法撤销。</p><div className="mt-3 flex gap-2"><button className={`${button} text-rose-700`} disabled={busy} onClick={() => void remove()}>{busy ? '删除中…' : '确认删除'}</button><button className={button} disabled={busy} onClick={() => setConfirmDelete(false)}>保留项目</button></div></div>}
        <fieldset disabled={busy}>
          <OpenAPIManager key={selected.id} projectId={selected.id} onBusyChange={setBusy} assetRevision={assetRevision} onCaseSaved={() => setAssetRevision(value => value + 1)} />
          <TestAssets key={'assets-' + selected.id} projectId={selected.id} revision={assetRevision} onBusyChange={setBusy} onChanged={() => setAssetRevision(value => value + 1)} />
        </fieldset>
      </div>}

      {draft && <form aria-label={editingId ? '编辑项目' : '新建项目'} onSubmit={event => void save(event)} className="mt-6 rounded-xl border border-indigo-100 bg-indigo-50/30 p-5">
        <h3 className="font-semibold">{editingId ? '编辑项目' : '新建项目'}</h3>
        <fieldset disabled={busy} className="mt-4 grid gap-4 disabled:opacity-60">
          <label className="text-sm font-medium">项目名称<input autoFocus className={input} required maxLength={100} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} placeholder="例如：订单服务" /></label>
          <label className="text-sm font-medium">API 基础地址<input className={input} required type="url" maxLength={2048} value={draft.base_url} onChange={event => setDraft({ ...draft, base_url: event.target.value })} placeholder="http://127.0.0.1:9000" /><span className="mt-1 block text-xs font-normal text-slate-500">支持 HTTP/HTTPS，可包含路径；请勿填写凭据、查询参数或片段。</span></label>
          <label className="text-sm font-medium">项目描述（可选）<textarea className={input} maxLength={2000} rows={3} value={draft.description} onChange={event => setDraft({ ...draft, description: event.target.value })} /></label>
          <div className="flex gap-2"><button type="submit" className={`${button} bg-indigo-600 text-white hover:bg-indigo-700`} disabled={busy || !draft.name.trim()}>{busy ? '保存中…' : '保存项目'}</button><button type="button" className={button} onClick={clearPanel}>取消</button></div>
        </fieldset>
      </form>}
    </section>
  )
}
