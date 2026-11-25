import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage, request } from './api'
import { ExecutionResult } from './ExecutionPanel'
import type { Execution } from './ExecutionPanel'

type Case = { id: string; name: string; description: string; operation_id: string; operation: { method: string; path: string }; input: unknown }
type Suite = { id: string; name: string; description: string; case_ids: string[] }
type Run = { id: string; suite_name: string; status: string; created_at: string; summary: { total: number; passed: number; failed: number; error: number; skipped: number } }
type RunDetail = Run & { snapshot: { name: string; input: unknown; base_url: string; method: string; path: string }[]; results: { name: string; status: string; error: string | null; execution: Execution | null; variables_used?: string[]; resolved_input?: unknown; exports?: Record<string, unknown> }[] }
type SuiteDraft = { id: string | null; name: string; description: string; case_ids: string[] }
const button = 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50'
const input = 'mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-indigo-500'
const labels: Record<string, string> = { passed: '通过', failed: '失败', error: '执行错误', skipped: '已跳过', pending: '等待', running: '运行中', interrupted: '已中断' }

export function TestAssets({ projectId, revision, onBusyChange, onChanged }: { projectId: string; revision: number; onBusyChange: (value: boolean) => void; onChanged: () => void }) {
  const [cases, setCases] = useState<Case[]>([])
  const [suites, setSuites] = useState<Suite[]>([])
  const [runs, setRuns] = useState<{ items: Run[]; total: number }>({ items: [], total: 0 })
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editingCase, setEditingCase] = useState<Case | null>(null)
  const [caseConfig, setCaseConfig] = useState('')
  const [suiteDraft, setSuiteDraft] = useState<SuiteDraft | null>(null)
  const [deleting, setDeleting] = useState<{ kind: 'test-cases' | 'test-suites'; id: string; name: string } | null>(null)
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [caseResult, setCaseResult] = useState<Execution | null>(null)
  const base = '/api/projects/' + projectId

  useEffect(() => () => onBusyChange(false), [onBusyChange])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError('')
    Promise.all([
      request<{ items: Case[] }>(base + '/test-cases', { signal: controller.signal }),
      request<{ items: Suite[] }>(base + '/test-suites', { signal: controller.signal }),
      request<{ items: Run[]; total: number }>(base + '/suite-runs?limit=5&offset=' + offset, { signal: controller.signal }),
    ]).then(([casePage, suitePage, runPage]) => {
      if (!controller.signal.aborted) { setCases(casePage.items); setSuites(suitePage.items); setRuns(runPage) }
    }).catch(caught => { if (!controller.signal.aborted) setLoadError(errorMessage(caught)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [base, offset, refresh, revision])

  async function action(task: () => Promise<void>) {
    if (busy) return
    setBusy(true); onBusyChange(true); setError(''); setNotice('')
    try { await task() }
    catch (caught) { setError(caught instanceof SyntaxError ? '执行配置必须是有效的 JSON。' : errorMessage(caught)) }
    finally { setBusy(false); onBusyChange(false) }
  }

  function changed(message: string) { setNotice(message); setOffset(0); onChanged() }
  function moveCase(index: number, delta: number) {
    if (!suiteDraft) return
    const ids = [...suiteDraft.case_ids]
    ;[ids[index], ids[index + delta]] = [ids[index + delta], ids[index]]
    setSuiteDraft({ ...suiteDraft, case_ids: ids })
  }
  async function saveCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingCase) return
    await action(async () => {
      await request(base + '/test-cases/' + editingCase.id, { method: 'PUT', body: JSON.stringify({ name: editingCase.name, description: editingCase.description, operation_id: editingCase.operation_id, input: JSON.parse(caseConfig) as unknown }) })
      setEditingCase(null); changed('用例已更新；既有运行快照保持不变。')
    })
  }
  async function saveSuite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!suiteDraft) return
    await action(async () => {
      await request(base + '/test-suites' + (suiteDraft.id ? '/' + suiteDraft.id : ''), { method: suiteDraft.id ? 'PUT' : 'POST', body: JSON.stringify({ name: suiteDraft.name, description: suiteDraft.description, case_ids: suiteDraft.case_ids }) })
      setSuiteDraft(null); changed('用例集已保存。')
    })
  }

  return <section aria-label="测试资产与回归" className="mt-8 rounded-xl border border-indigo-100 bg-white p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="text-lg font-semibold">测试资产与回归</h4><p className="mt-1 text-xs text-slate-500">保存用例，按指定顺序一键回归。每项目最多 100 条用例、50 个用例集，每集最多 10 条。</p></div><button className={button} disabled={busy || loading} onClick={() => setRefresh(value => value + 1)}>刷新测试资产</button></div>
    <p className="mt-3 text-xs text-slate-500">在上方接口执行表单中配置请求和断言，填写用例名称后点击“保存为测试用例”。用例保存原始配置，请使用测试数据。</p>
    <p className="mt-2 text-xs text-slate-500">流程示例：创建订单用例设置 extract 为 {'{"order_id":"/id"}'}，后续查询用例的路径参数设置为 {'{"order_id":"{{order_id}}"}'}。生产变量的用例必须排在前面；上游失败时依赖项会跳过。</p>
    {busy && <p role="status" className="mt-3 text-sm text-indigo-700">正在处理，请勿重复提交。用例集总执行时间最多 30 秒。</p>}
    {notice && <p role="status" className="mt-3 text-sm text-emerald-700">{notice}</p>}
    {error && <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p>}
    {loadError && <p role="alert" className="mt-3 text-sm text-rose-700">测试资产加载失败：{loadError}</p>}
    {loading ? <p role="status" className="mt-4 text-sm text-slate-500">正在加载测试资产…</p> : loadError ? null : <>
      <h5 className="mt-6 font-semibold">已保存用例 · {cases.length}</h5>
      {cases.length ? <ul className="mt-3 space-y-3">{cases.map(item => <li key={item.id} className="rounded-lg border border-slate-200 p-3"><p className="break-words text-sm font-medium">{item.name}</p><p className="mt-1 break-all font-mono text-xs text-slate-500">{item.operation.method} {item.operation.path}</p><div className="mt-3 flex flex-wrap gap-2">
        <button className={button} disabled={busy} aria-label={'运行用例 ' + item.name} onClick={() => void action(async () => { const record = await request<Execution>(base + '/test-cases/' + item.id + '/execute', { method: 'POST' }, 15000); setCaseResult(record); changed('用例执行完成，已保存执行记录。') })}>运行用例</button>
        <button className={button} disabled={busy} aria-label={'编辑用例 ' + item.name} onClick={() => { setEditingCase({ ...item }); setCaseConfig(JSON.stringify(item.input, null, 2)); setError('') }}>编辑</button>
        <button className={button + ' text-rose-700'} disabled={busy} aria-label={'删除用例 ' + item.name} onClick={() => setDeleting({ kind: 'test-cases', id: item.id, name: item.name })}>删除</button>
      </div></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">暂无已保存用例。</p>}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3"><h5 className="font-semibold">用例集 · {suites.length}</h5><button className={button} disabled={busy} onClick={() => setSuiteDraft({ id: null, name: '', description: '', case_ids: [] })}>新建用例集</button></div>
      {suites.length ? <ul className="mt-3 space-y-3">{suites.map(item => <li key={item.id} className="rounded-lg border border-slate-200 p-3"><p className="break-words text-sm font-medium">{item.name} · {item.case_ids.length} 条用例</p><div className="mt-3 flex flex-wrap gap-2">
        <button className={button} disabled={busy || !item.case_ids.length} aria-label={'运行用例集 ' + item.name} onClick={() => void action(async () => { setSelectedRun(null); const run = await request<RunDetail>(base + '/test-suites/' + item.id + '/run', { method: 'POST' }, 45000); setSelectedRun(run); changed('用例集运行完成：' + (labels[run.status] || run.status)) })}>运行用例集</button>
        <button className={button} disabled={busy} aria-label={'编辑用例集 ' + item.name} onClick={() => setSuiteDraft({ ...item, case_ids: [...item.case_ids] })}>编辑</button>
        <button className={button + ' text-rose-700'} disabled={busy} aria-label={'删除用例集 ' + item.name} onClick={() => setDeleting({ kind: 'test-suites', id: item.id, name: item.name })}>删除</button>
      </div></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">暂无用例集。创建后可选择用例并调整执行顺序。</p>}
      <h5 className="mt-6 font-semibold">回归运行记录 · {runs.total}</h5>
      {runs.items.length ? <ul className="mt-3 space-y-2">{runs.items.map(run => <li key={run.id}><button className={button + ' w-full text-left'} disabled={busy} onClick={() => void action(async () => { setSelectedRun(await request<RunDetail>(base + '/suite-runs/' + run.id)) })}>{run.suite_name} · {labels[run.status] || run.status} · {run.summary.passed}/{run.summary.total} 通过 · {new Date(run.created_at).toLocaleString('zh-CN')}</button></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">暂无回归运行记录。</p>}
      <div className="mt-3 flex gap-2"><button className={button} disabled={busy || !offset} onClick={() => setOffset(value => Math.max(0, value - 5))}>上一页回归</button><button className={button} disabled={busy || offset + 5 >= runs.total} onClick={() => setOffset(value => value + 5)}>下一页回归</button></div>
    </>}

    {deleting && <div className="mt-4 rounded-lg border border-rose-200 p-4"><p className="text-sm">确定删除“{deleting.name}”？编辑资产会被移除，既有运行历史仍保留。</p><div className="mt-3 flex gap-2"><button className={button + ' text-rose-700'} disabled={busy} onClick={() => void action(async () => { await request(base + '/' + deleting.kind + '/' + deleting.id, { method: 'DELETE' }); setDeleting(null); changed('测试资产已删除。') })}>确认删除测试资产</button><button className={button} disabled={busy} onClick={() => setDeleting(null)}>取消删除</button></div></div>}
    {editingCase && <form aria-label="编辑保存的用例" className="mt-5 rounded-lg border border-indigo-200 p-4" onSubmit={event => void saveCase(event)}>
      <h5 className="font-semibold">编辑用例</h5><fieldset disabled={busy} className="mt-3 grid gap-3">
        <label className="text-sm">用例名称<input className={input} required maxLength={100} value={editingCase.name} onChange={event => setEditingCase({ ...editingCase, name: event.target.value })} /></label>
        <label className="text-sm">用例描述<textarea className={input} maxLength={2000} value={editingCase.description} onChange={event => setEditingCase({ ...editingCase, description: event.target.value })} /></label>
        <p className="text-xs text-slate-500">{editingCase.operation.method} {editingCase.operation.path} · 保存时会重新校验当前接口定义。</p>
        <label className="text-sm">请求与断言配置 JSON<textarea className={input + ' font-mono text-xs'} rows={12} required maxLength={70000} value={caseConfig} onChange={event => setCaseConfig(event.target.value)} /><span className="mt-1 block text-xs text-slate-500">包含 path_params、query_params、body、expected_status、checks、timeout_seconds、extract。引用变量需使用完整字段值 {'{{name}}'}；不支持字符串拼接。</span></label>
        <div className="flex gap-2"><button className={button} type="submit">保存用例修改</button><button className={button} type="button" onClick={() => setEditingCase(null)}>取消编辑用例</button></div>
      </fieldset>
    </form>}
    {suiteDraft && <form aria-label="编辑用例集" className="mt-5 rounded-lg border border-indigo-200 p-4" onSubmit={event => void saveSuite(event)}>
      <h5 className="font-semibold">{suiteDraft.id ? '编辑用例集' : '新建用例集'}</h5><fieldset disabled={busy} className="mt-3 grid gap-3">
        <label className="text-sm">用例集名称<input className={input} required maxLength={100} value={suiteDraft.name} onChange={event => setSuiteDraft({ ...suiteDraft, name: event.target.value })} /></label>
        <label className="text-sm">用例集描述<textarea className={input} maxLength={2000} value={suiteDraft.description} onChange={event => setSuiteDraft({ ...suiteDraft, description: event.target.value })} /></label>
        <p className="text-sm font-medium">选择用例（最多 10 条）</p>
        {cases.map(item => <label key={item.id} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={suiteDraft.case_ids.includes(item.id)} disabled={!suiteDraft.case_ids.includes(item.id) && suiteDraft.case_ids.length >= 10} onChange={event => setSuiteDraft({ ...suiteDraft, case_ids: event.target.checked ? [...suiteDraft.case_ids, item.id] : suiteDraft.case_ids.filter(id => id !== item.id) })} />{item.name}</label>)}
        <p className="text-sm font-medium">执行顺序</p>
        <ol className="space-y-2">{suiteDraft.case_ids.map((id, index) => <li key={id} className="flex flex-wrap items-center gap-2 text-sm"><span>{index + 1}. {cases.find(item => item.id === id)?.name || '用例已不存在'}</span><button type="button" className={button} aria-label={'第 ' + (index + 1) + ' 条用例上移'} disabled={index === 0} onClick={() => moveCase(index, -1)}>上移</button><button type="button" className={button} aria-label={'第 ' + (index + 1) + ' 条用例下移'} disabled={index === suiteDraft.case_ids.length - 1} onClick={() => moveCase(index, 1)}>下移</button></li>)}</ol>
        <div className="flex gap-2"><button className={button} type="submit">保存用例集</button><button className={button} type="button" onClick={() => setSuiteDraft(null)}>取消编辑用例集</button></div>
      </fieldset>
    </form>}
    {caseResult && <div className="mt-5"><button className={button} onClick={() => setCaseResult(null)}>关闭用例执行结果</button><ExecutionResult value={caseResult} /></div>}
    {selectedRun && <section aria-label="回归运行详情" className="mt-5 rounded-lg border border-indigo-200 p-4"><div className="flex flex-wrap justify-between gap-2"><h5 className="font-semibold">{selectedRun.suite_name} · {labels[selectedRun.status] || selectedRun.status}</h5><button className={button} onClick={() => setSelectedRun(null)}>关闭回归详情</button></div><p className="mt-3 text-sm">共 {selectedRun.summary.total} 条，通过 {selectedRun.summary.passed}，失败 {selectedRun.summary.failed}，错误 {selectedRun.summary.error}，跳过 {selectedRun.summary.skipped}。</p><p className="mt-1 break-all text-xs text-slate-400">运行 ID：{selectedRun.id} · {new Date(selectedRun.created_at).toLocaleString('zh-CN')}</p>
      {selectedRun.snapshot.map((snapshot, index) => <details key={index} className="mt-3 rounded-lg border border-slate-200 p-3"><summary className="cursor-pointer break-words text-sm font-medium">{index + 1}. {snapshot.name} · {labels[selectedRun.results[index]?.status] || selectedRun.results[index]?.status}</summary><p className="mt-2 break-all font-mono text-xs">{snapshot.method} {snapshot.path} · {snapshot.base_url}</p>
        <details className="mt-2"><summary className="cursor-pointer text-xs">用例配置快照（含模板）</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(snapshot.input, null, 2)}</pre></details>
        {selectedRun.results[index]?.variables_used && <p className="mt-2 text-xs text-slate-500">引用变量：{selectedRun.results[index].variables_used!.join(', ') || '无'}</p>}
        {selectedRun.results[index]?.resolved_input != null && <details className="mt-2" open><summary className="cursor-pointer text-xs">实际请求输入</summary><pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selectedRun.results[index].resolved_input, null, 2)}</pre></details>}
        {selectedRun.results[index]?.exports && Object.keys(selectedRun.results[index].exports!).length > 0 && <details className="mt-2" open><summary className="cursor-pointer text-xs">本步骤导出变量</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(selectedRun.results[index].exports, null, 2)}</pre></details>}
        {selectedRun.results[index]?.error && <p className="mt-2 text-sm text-amber-800">{selectedRun.results[index].error}</p>}{selectedRun.results[index]?.execution && <ExecutionResult value={selectedRun.results[index].execution!} />}</details>)}
    </section>}
  </section>
}
