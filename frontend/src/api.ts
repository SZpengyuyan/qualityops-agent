export type ProjectInput = { name: string; description: string; base_url: string }
export type Project = ProjectInput & { id: string; created_at: string; updated_at: string }
export type ProjectPage = { items: Project[]; total: number; limit: number; offset: number }

export async function request<T>(path: string, options: RequestInit = {}, timeoutMs = 8000): Promise<T> {
  const timeout = AbortSignal.timeout(timeoutMs)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout
  const response = await fetch(path, {
    ...options,
    signal,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  })
  if (!response.ok) {
    if (response.status === 422 || response.status === 409) {
      const body: unknown = await response.json().catch(() => null)
      if (typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string') throw new Error(body.detail)
      throw new Error('输入格式不正确，请检查字段内容、长度和格式。')
    }
    if (response.status === 404) throw new Error('项目不存在，可能已被删除。请刷新列表。')
    throw new Error(`请求失败（HTTP ${response.status}），请稍后重试。`)
  }
  return response.status === 204 ? undefined as T : await response.json() as T
}

export function errorMessage(error: unknown): string {
  if (error instanceof DOMException && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
    return '请求超时，请刷新列表确认最新状态后再试。'
  }
  return error instanceof Error ? error.message : '网络异常，请确认后端连接。'
}
