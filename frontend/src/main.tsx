import { StrictMode, useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ProjectManager } from './ProjectManager'
import './index.css'

type Check = { ok: boolean; detail: string }
type Health = { api: Check; db: Check; checkedAt: string }

async function checkEndpoint(path: string, field: string, expected: string, signal: AbortSignal): Promise<Check> {
  try {
    const response = await fetch(path, { signal, cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const body: unknown = await response.json()
    if (typeof body !== 'object' || body === null || !('status' in body) || body.status !== 'ok'
      || !(field in body) || (body as Record<string, unknown>)[field] !== expected) {
      throw new Error('响应格式异常')
    }
    return { ok: true, detail: '连接正常' }
  } catch (error) {
    return { ok: false, detail: error instanceof Error ? error.message : '连接失败' }
  }
}

function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null)
  const [checking, setChecking] = useState(true)
  const active = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setChecking(true)
    const timeout = window.setTimeout(() => controller.abort(), 5000)
    try {
      const [api, db] = await Promise.all([
        checkEndpoint('/api/health', 'service', 'qualityops-api', controller.signal),
        checkEndpoint('/api/health/db', 'database', 'sqlite', controller.signal),
      ])
      if (active.current !== controller) return
      setHealth({ api, db, checkedAt: new Date().toLocaleTimeString('zh-CN', { hour12: false }) })
      setChecking(false)
    } finally {
      window.clearTimeout(timeout)
    }
  }, [])

  useEffect(() => {
    void refresh()
    return () => { active.current?.abort(); active.current = null }
  }, [refresh])

  const connected = health?.api.ok && health?.db.ok
  const status = checking ? 'Checking…' : connected ? 'Connected' : 'Disconnected'

  return (
    <div className="min-h-screen text-slate-800 md:flex">
      <aside className="flex shrink-0 flex-col bg-[#101827] px-6 py-7 text-white md:min-h-screen md:w-64">
        <div className="flex items-center gap-3 text-lg font-semibold tracking-tight">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500 text-sm">QO</span>
          QualityOps <span className="text-indigo-300">/</span>
        </div>
        <p className="mt-7 text-[10px] font-semibold tracking-[0.2em] text-slate-500">WORKSPACE</p>
        <div aria-current="page" className="mt-3 rounded-lg border border-slate-700 bg-slate-800 px-4 py-3 text-sm font-medium">◫ &nbsp; Overview</div>
        <div className="mt-auto hidden border-t border-slate-800 pt-5 md:block">
          <p className="text-xs text-slate-400">QualityOps Agent</p>
          <p className="mt-1 text-xs text-slate-500">v0.1.0 · Local development</p>
        </div>
      </aside>

      <main className="mx-auto w-full max-w-7xl p-6 md:p-12">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-8">
          <div><p className="text-xs font-semibold tracking-[0.15em] text-indigo-600">ENGINEERING WORKSPACE</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">Overview</h1>
            <p className="mt-2 text-sm text-slate-500">智能质量保障平台 · 项目工作台</p></div>
          <span className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-500">DAY 02 / 14</span>
        </header>

        <section aria-labelledby="system-title" className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div><h2 id="system-title" className="text-lg font-semibold">系统连接</h2><p className="mt-1 text-sm text-slate-500">实时检查 API 服务和 SQLite 数据库</p></div>
            <div className="flex items-center gap-3">
              <span role="status" className={`rounded-full px-3 py-1.5 text-xs font-semibold ${checking ? 'bg-slate-100 text-slate-600' : connected ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>● {status}</span>
              <button onClick={() => void refresh()} disabled={checking} className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-indigo-500 disabled:opacity-50">重新检查</button>
            </div>
          </div>
          <div className="mt-7 grid gap-4 sm:grid-cols-2">
            {([{ name: 'Backend API', path: '/api/health', result: health?.api, technology: 'FastAPI' },
              { name: 'Database', path: '/api/health/db', result: health?.db, technology: 'SQLite · SQLAlchemy' }]).map(item => (
              <div key={item.path} className="rounded-xl border border-slate-200 bg-slate-50/60 p-5">
                <p className="text-xs text-slate-500">{item.technology}</p>
                <div className="mt-3 flex items-center justify-between gap-2"><h3 className="font-semibold">{item.name}</h3><span className={`text-xs ${checking ? 'text-slate-500' : item.result?.ok ? 'text-emerald-700' : 'text-rose-700'}`}>{checking ? '检查中' : item.result?.detail}</span></div>
                <code className="mt-4 block text-xs text-slate-500">GET {item.path}</code>
              </div>
            ))}
          </div>
          <p className="mt-5 text-xs text-slate-400">{checking ? '正在获取最新状态…' : `最后检查于 ${health?.checkedAt} · 手动刷新更新状态`}</p>
          {!checking && !connected && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">连接未就绪。请确认后端已在 127.0.0.1:8000 启动，然后重新检查。</p>}
        </section>

        <ProjectManager />
        <footer className="mt-10 text-xs text-slate-400">QualityOps Agent / Build confidence, one check at a time.</footer>
      </main>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><Dashboard /></StrictMode>)
