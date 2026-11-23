import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import { errorMessage, request } from './api'
import { ExecutionHistory, ExecutionPanel } from './ExecutionPanel'

type DocumentInfo = { title: string; api_version: string; openapi_version: string; imported_at: string; operation_count: number; tags: string[] }
type Operation = {
  id: string; method: string; path: string; operation_id: string | null; summary: string; description: string
  tags: string[]; deprecated: boolean; parameters: Record<string, unknown>[]
  request_body: Record<string, unknown> | null; responses: Record<string, unknown>
  security: Record<string, unknown>[]; servers: Record<string, unknown>[]
}
type OperationPage = { items: Operation[]; total: number }
const button = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:cursor-wait disabled:opacity-50'
const input = 'rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-indigo-500'
const pageSize = 10

export function OpenAPIManager({ projectId, onBusyChange }: { projectId: string; onBusyChange: (busy: boolean) => void }) {
  const [document, setDocument] = useState<DocumentInfo | null>(null)
  const [page, setPage] = useState<OperationPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [content, setContent] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [replace, setReplace] = useState(false)
  const [busy, setBusy] = useState(false)
  const [method, setMethod] = useState('')
  const [tag, setTag] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [operationId, setOperationId] = useState<string | null>(null)
  const [operation, setOperation] = useState<Operation | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [executionRevision, setExecutionRevision] = useState(0)
  const changeExecutionBusy = useCallback((value: boolean) => { setBusy(value); onBusyChange(value) }, [onBusyChange])
  const base = `/api/projects/${projectId}`

  useEffect(() => () => onBusyChange(false), [onBusyChange])

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ method, tag, q: search, limit: String(pageSize), offset: String(offset) })
    setLoading(true); setLoadError('')
    Promise.all([
      request<DocumentInfo | null>(`${base}/openapi`, { signal: controller.signal }),
      request<OperationPage>(`${base}/operations?${params}`, { signal: controller.signal }),
    ]).then(([metadata, result]) => {
      if (!controller.signal.aborted) { setDocument(metadata); setPage(result) }
    }).catch(error => { if (!controller.signal.aborted) setLoadError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [base, method, tag, search, offset, revision])

  useEffect(() => {
    setOperation(null)
    if (!operationId) { setDetailLoading(false); return }
    const controller = new AbortController()
    setDetailLoading(true)
    request<Operation>(`${base}/operations/${operationId}`, { signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setOperation(result) })
      .catch(error => { if (!controller.signal.aborted) setActionError(errorMessage(error)) })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [base, operationId])

  async function readFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setActionError('')
    if (file.size > 1024 * 1024) { setActionError('文件不能超过 1 MiB。'); return }
    try { setContent(await file.text()) }
    catch { setActionError('无法读取文件，请重新选择。') }
  }

  async function importDocument(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !content.trim() || (document && !replace)) return
    setBusy(true); onBusyChange(true); setActionError(''); setNotice('')
    try {
      if (new TextEncoder().encode(content).length > 1024 * 1024) throw new Error('文档不能超过 1 MiB。')
      const result = await request<DocumentInfo>(`${base}/openapi`, { method: 'PUT', body: JSON.stringify({ content }) })
      setDocument(result); setNotice(`导入成功，共解析 ${result.operation_count} 个接口。`)
      setContent(''); setShowImport(false); setReplace(false); setOperationId(null)
      setMethod(''); setTag(''); setSearch(''); setSearchInput(''); setOffset(0); setRevision(value => value + 1)
    } catch (error) { setActionError(errorMessage(error)) }
    finally { setBusy(false); onBusyChange(false) }
  }

  return (
    <section aria-labelledby={`openapi-${projectId}`} className="mt-6 border-t border-indigo-100 pt-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h4 id={`openapi-${projectId}`} className="font-semibold">接口文档与目录</h4><p className="mt-1 text-xs text-slate-500">OpenAPI 3.0/3.1 · JSON · 最多 1 MiB / 500 个接口</p></div>
        <div className="flex gap-2"><button className={button} disabled={busy || loading} onClick={() => { setOperationId(null); setRevision(value => value + 1) }}>刷新目录</button><button className={button} disabled={busy || loading || !!loadError} onClick={() => { setShowImport(value => !value); setReplace(false); setActionError('') }}>{showImport ? '收起导入' : document ? '重新导入文档' : '导入 OpenAPI'}</button></div>
      </div>
      {notice && <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
      {loadError && <p role="alert" className="mt-4 text-sm text-rose-700">目录加载失败：{loadError}</p>}
      {actionError && <p role="alert" className="mt-4 text-sm text-rose-700">{actionError}</p>}
      {showImport && <form aria-label="导入 OpenAPI 文档" onSubmit={event => void importDocument(event)} className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
        <fieldset disabled={busy} className="grid gap-4">
          <label className="text-sm">选择本地 JSON 文件<input type="file" accept=".json,application/json" onChange={event => void readFile(event)} className="mt-2 block w-full text-sm" /></label>
          <label className="text-sm">或粘贴 OpenAPI JSON<textarea required rows={8} value={content} maxLength={1024 * 1024} onChange={event => setContent(event.target.value)} className={`${input} mt-2 block w-full font-mono text-xs`} placeholder={'{ "openapi": "3.0.3", "info": { ... }, "paths": { ... } }'} /></label>
          <p className="text-xs text-slate-500">支持文档内部 #/ 引用；暂不支持 YAML、外部引用及自定义 Schema 方言。导入不会访问待测服务。</p>
          {document && <label className="flex items-start gap-2 text-sm text-amber-800"><input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} className="mt-1" />我确认用新文档替换当前接口目录；校验失败会保留原目录。</label>}
          <button type="submit" className={`${button} justify-self-start`} disabled={busy || !content.trim() || (!!document && !replace)}>{busy ? '校验并导入中…' : '校验并导入'}</button>
        </fieldset>
      </form>}

      {loading ? <p role="status" className="mt-5 text-sm text-slate-500">正在加载接口目录…</p> : loadError ? null : !document ? <p className="mt-5 rounded-lg border border-dashed border-slate-300 p-5 text-sm text-slate-500">尚未导入接口文档。导入后可查看参数、请求体和响应定义。</p> : <>
        <p className="mt-5 break-words text-sm font-medium">{document.title} <span className="font-normal text-slate-500">v{document.api_version} · OpenAPI {document.openapi_version} · 共 {document.operation_count} 个接口</span></p>
        <p className="mt-1 text-xs text-slate-400">导入于 {new Date(document.imported_at).toLocaleString('zh-CN')}</p>
        <form className="mt-4 flex flex-wrap gap-2" aria-label="筛选接口" onSubmit={event => { event.preventDefault(); setSearch(searchInput.trim()); setOffset(0); setOperationId(null) }}>
          <label className="sr-only" htmlFor={`method-${projectId}`}>HTTP 方法</label><select id={`method-${projectId}`} className={input} disabled={busy} value={method} onChange={event => { setMethod(event.target.value); setOffset(0); setOperationId(null) }}><option value="">所有方法</option>{['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE'].map(item => <option key={item}>{item}</option>)}</select>
          <label className="sr-only" htmlFor={`tag-${projectId}`}>接口标签</label><select id={`tag-${projectId}`} className={input} disabled={busy} value={tag} onChange={event => { setTag(event.target.value); setOffset(0); setOperationId(null) }}><option value="">所有标签</option>{document.tags.map(item => <option key={item}>{item}</option>)}</select>
          <label className="sr-only" htmlFor={`search-${projectId}`}>搜索接口</label><input id={`search-${projectId}`} className={`${input} min-w-0 flex-1`} maxLength={200} disabled={busy} value={searchInput} onChange={event => setSearchInput(event.target.value)} placeholder="搜索路径、摘要或 operationId" /><button className={button} disabled={busy}>搜索</button>
        </form>
        {page?.items.length ? <ul className="mt-4 space-y-2">{page.items.map(item => <li key={item.id}><button disabled={busy} onClick={() => { setOperationId(item.id); setActionError('') }} className="flex w-full flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left hover:border-indigo-300 focus-visible:outline-2 focus-visible:outline-indigo-500"><span className={`rounded px-2 py-1 text-xs font-bold ${item.method === 'GET' ? 'bg-emerald-50 text-emerald-700' : 'bg-indigo-50 text-indigo-700'}`}>{item.method}</span><code className="min-w-0 break-all text-sm">{item.path}</code><span className="min-w-0 break-words text-xs text-slate-500">{item.summary || item.operation_id || '无摘要'}{item.deprecated ? ' · 已弃用' : ''}</span></button></li>)}</ul> : <p className="mt-4 text-sm text-slate-500">没有匹配的接口。</p>}
        {page && <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>匹配 {page.total} 个 · 第 {Math.floor(offset / pageSize) + 1} 页</span><div className="flex gap-2"><button className={button} disabled={busy || !offset} onClick={() => { setOffset(value => Math.max(0, value - pageSize)); setOperationId(null) }}>上一页接口</button><button className={button} disabled={busy || offset + pageSize >= page.total} onClick={() => { setOffset(value => value + pageSize); setOperationId(null) }}>下一页接口</button></div></div>}
      </>}
      {detailLoading && <p role="status" className="mt-4 text-sm text-slate-500">正在加载接口详情…</p>}
      {operation && <div className="mt-5 min-w-0 rounded-xl border border-indigo-200 bg-white p-4"><div className="flex flex-wrap justify-between gap-2"><h5 className="break-all font-mono text-sm font-semibold">{operation.method} {operation.path}</h5><button className={button} disabled={busy} onClick={() => setOperationId(null)}>关闭接口详情</button></div>
        <p className="mt-2 break-words text-sm">{operation.summary}</p><p className="mt-2 whitespace-pre-wrap break-words text-xs text-slate-500">{operation.description}</p>
        <p className="mt-2 break-words text-xs text-slate-500">operationId: {operation.operation_id || '未定义'} · 标签: {operation.tags.join(', ') || '无'}</p>
        {([['参数（已合并路径级与操作级）', operation.parameters], ['请求体', operation.request_body], ['响应定义', operation.responses], ['认证要求', operation.security], ['服务地址定义', operation.servers]] as const).map(([title, value]) => <details key={title} open={title === '参数（已合并路径级与操作级）' || title === '响应定义'} className="mt-3 rounded-lg border border-slate-200 p-3"><summary className="cursor-pointer text-sm font-medium">{title}</summary><pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-all font-mono text-xs text-slate-600">{value === null ? '未定义' : JSON.stringify(value, null, 2)}</pre></details>)}
        <p className="mt-3 text-xs text-slate-400">Schema 内的 $ref 保留为引用；只有点击下方发送按钮才会执行接口。</p>
        <ExecutionPanel key={operation.id} projectId={projectId} operation={operation} disabled={busy} onBusyChange={changeExecutionBusy} onExecuted={() => setExecutionRevision(value => value + 1)} />
      </div>}
      <ExecutionHistory projectId={projectId} revision={executionRevision} />
    </section>
  )
}
