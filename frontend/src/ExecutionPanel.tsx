import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage, request } from './api'

type Execution = {
  id: string; status: 'passed' | 'failed' | 'error'; duration_ms: number; created_at: string
  request: { method: string; path: string }; response: { status_code: number; body: unknown } | null
  assertions: { type: string; pointer?: string; expected: unknown; actual: unknown; passed: boolean; error?: string }[]
  error: string | null
}
const button = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50'
const input = 'mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs focus-visible:outline-2 focus-visible:outline-indigo-500'
const statusNames = { passed: '通过', failed: '断言失败', error: '执行错误' }

function ExecutionResult({ value }: { value: Execution }) {
  return <div className="mt-4 rounded-lg border border-slate-200 bg-white p-4">
    <p role="status" className={'font-semibold ' + (value.status === 'passed' ? 'text-emerald-700' : value.status === 'failed' ? 'text-rose-700' : 'text-amber-800')}>{statusNames[value.status]} · {value.duration_ms} ms{value.response ? ' · HTTP ' + value.response.status_code : ''}</p>
    <p className="mt-2 break-all text-xs text-slate-400">记录 ID：{value.id} · {new Date(value.created_at).toLocaleString('zh-CN')}</p>
    {value.error && <p role="alert" className="mt-3 text-sm text-amber-800">{value.error}</p>}
    <ul className="mt-3 space-y-2">{value.assertions.map((check, index) => <li key={index} className="rounded-lg bg-slate-50 p-3 text-xs"><p className={check.passed ? 'text-emerald-700' : 'text-rose-700'}>{check.passed ? '✓' : '×'} {check.type === 'status' ? '状态码' : 'JSON ' + (check.pointer || '(根节点)')}</p><pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all">期望：{JSON.stringify(check.expected)}{'\n'}实际：{JSON.stringify(check.actual)}{check.error ? '\n' + check.error : ''}</pre></li>)}</ul>
    {value.response && <details open className="mt-3"><summary className="cursor-pointer text-sm">响应内容</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-slate-50 p-3 text-xs">{JSON.stringify(value.response.body, null, 2)}</pre></details>}
  </div>
}

function stringMap(text: string): Record<string, string> {
  const value: unknown = JSON.parse(text)
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.values(value).some(item => typeof item !== 'string')) throw new Error('路径和查询参数必须是 JSON 对象，且所有值为字符串。')
  return value as Record<string, string>
}

export function ExecutionPanel({ projectId, operation, disabled, onBusyChange, onExecuted }: {
  projectId: string; operation: { id: string; method: string; path: string; responses: Record<string, unknown> }
  disabled: boolean; onBusyChange: (busy: boolean) => void; onExecuted: () => void
}) {
  const [pathParams, setPathParams] = useState(() => JSON.stringify(Object.fromEntries([...operation.path.matchAll(/\{([^{}]+)\}/g)].map(match => [match[1], ''])), null, 2))
  const [queryParams, setQueryParams] = useState('{}')
  const [body, setBody] = useState('')
  const [expectedStatus, setExpectedStatus] = useState(() => Number(Object.keys(operation.responses).find(code => /^2\d\d$/.test(code)) || 200))
  const [checks, setChecks] = useState('[]')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<Execution | null>(null)
  useEffect(() => () => onBusyChange(false), [onBusyChange])

  async function execute(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || disabled) return
    setError(''); setResult(null)
    try {
      const payload = { path_params: stringMap(pathParams), query_params: stringMap(queryParams), body: body.trim() ? JSON.parse(body) as unknown : null, expected_status: expectedStatus, checks: JSON.parse(checks) as unknown }
      setBusy(true); onBusyChange(true)
      const value = await request<Execution>('/api/projects/' + projectId + '/operations/' + operation.id + '/execute', { method: 'POST', body: JSON.stringify(payload) }, 15000)
      setResult(value); onExecuted()
    } catch (caught) { setError(caught instanceof SyntaxError ? 'JSON 格式不正确，请检查参数、请求体和断言。' : errorMessage(caught)) }
    finally { setBusy(false); onBusyChange(false) }
  }

  return <section className="mt-5 border-t border-slate-200 pt-5" aria-label="接口执行">
    <h6 className="font-semibold">执行与断言</h6><p className="mt-2 text-xs text-slate-500">将向项目基础地址发送真实请求。请使用测试服务；请求不会自动重试。当前支持无认证接口与 JSON 请求体。</p>
    <form onSubmit={event => void execute(event)} className="mt-4">
      <fieldset disabled={busy || disabled} className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm">路径参数 JSON<textarea className={input} rows={3} value={pathParams} onChange={event => setPathParams(event.target.value)} maxLength={10000} /></label>
        <label className="text-sm">查询参数 JSON<textarea className={input} rows={3} value={queryParams} onChange={event => setQueryParams(event.target.value)} maxLength={10000} /></label>
        {!['GET', 'HEAD', 'OPTIONS'].includes(operation.method) && <label className="text-sm sm:col-span-2">JSON 请求体<textarea className={input} rows={4} maxLength={60000} value={body} onChange={event => setBody(event.target.value)} placeholder={'{"product_id":"demo","quantity":1}'} /></label>}
        <label className="text-sm">期望状态码<input className={input} required type="number" min={100} max={599} value={expectedStatus} onChange={event => setExpectedStatus(Number(event.target.value))} /></label>
        <label className="text-sm">JSON 相等断言<textarea className={input} rows={4} value={checks} maxLength={20000} onChange={event => setChecks(event.target.value)} placeholder={'[{"pointer":"/status","expected":"created"}]'} /><span className="mt-1 block text-xs text-slate-400">使用 JSON Pointer，例如 /status 或 /items/0/id；[] 表示只检查状态码。</span></label>
        <button className={button + ' justify-self-start sm:col-span-2'} type="submit" disabled={busy || disabled}>{busy ? '执行中…' : '发送请求并执行断言'}</button>
      </fieldset>
    </form>
    {error && <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p>}
    {result && <ExecutionResult value={result} />}
  </section>
}

export function ExecutionHistory({ projectId, revision }: { projectId: string; revision: number }) {
  const [page, setPage] = useState<{ items: Execution[]; total: number } | null>(null)
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Execution | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    request<{ items: Execution[]; total: number }>('/api/projects/' + projectId + '/executions?limit=5&offset=' + offset, { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setPage(value) })
      .catch(caught => { if (!controller.signal.aborted) setError(errorMessage(caught)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId, offset, revision, refresh])
  return <section aria-label="执行历史" className="mt-6 border-t border-indigo-100 pt-5">
    <div className="flex items-center justify-between gap-2"><h5 className="font-semibold">执行历史</h5><button className={button} disabled={loading} onClick={() => { setOffset(0); setRefresh(value => value + 1); setSelected(null) }}>刷新执行记录</button></div>
    {loading ? <p role="status" className="mt-3 text-sm text-slate-500">正在读取执行记录…</p> : error ? <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p> : <>
      {page?.items.length ? <ul className="mt-3 space-y-2">{page.items.map(item => <li key={item.id}><button className={button + ' w-full text-left'} onClick={() => setSelected(item)}>{statusNames[item.status]} · {item.request.method} {item.request.path} · {item.duration_ms} ms <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString('zh-CN')}</span></button></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">暂无执行记录。</p>}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500"><span>共 {page?.total || 0} 条记录</span><div className="flex gap-2"><button className={button} disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 5))}>上一页记录</button><button className={button} disabled={offset + 5 >= (page?.total || 0)} onClick={() => setOffset(value => value + 5)}>下一页记录</button></div></div>
    </>}
    {selected && <><button className={button + ' mt-3'} onClick={() => setSelected(null)}>关闭记录详情</button><ExecutionResult value={selected} /></>}
  </section>
}
