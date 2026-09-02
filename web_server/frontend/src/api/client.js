/*
 * API fetch 封装（design/04 §4）：
 * - 信封解包：success===false → 抛 {code, message} 并 toast
 * - X-API-Key 注入：POST 必需（服务端 fail-closed）；GET 带上也无害
 * - 8s 超时（04 §6 弱网预算）；429 读 Retry-After 提示
 * - 内置极简 toast 队列（右上角堆叠，10 §6：成功/失败，失败常驻）
 */
import { reactive } from 'vue'

const KEY_STORAGE = 'trendradar_api_key'

/* ---------------- toast ---------------- */

export const toasts = reactive([])
let toastSeq = 0

export function toast(message, { type = 'error', sticky = false } = {}) {
  const id = ++toastSeq
  toasts.push({ id, message, type })
  if (!sticky) {
    // 10 §6：3s 自动消失，失败态常驻（此处 sticky=false 的成功/加载型才自动消）
    setTimeout(() => dismissToast(id), 3000)
  }
  return id
}

export function dismissToast(id) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

function toastError(err) {
  // 失败态常驻（10 §6），需用户手动关
  toast(err.message || String(err), { type: 'error', sticky: true })
}

/* ---------------- 请求 ---------------- */

export class ApiError extends Error {
  constructor(code, message, status, retryAfter) {
    super(message)
    this.code = code
    this.status = status
    this.retryAfter = retryAfter
  }
}

async function request(path, { method = 'GET', body, timeout = 8000, silent = false } = {}) {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeout)
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const apiKey = localStorage.getItem(KEY_STORAGE)
  if (apiKey) headers['X-API-Key'] = apiKey

  try {
    const res = await fetch(path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })

    if (res.status === 429) {
      const retry = res.headers.get('retry-after')
      throw new ApiError('RATE_LIMITED', `请求过于频繁，请 ${retry || 60} 秒后重试`, 429, retry)
    }

    let envelope = null
    try {
      envelope = await res.json()
    } catch {
      throw new ApiError('BAD_RESPONSE', `服务返回异常（HTTP ${res.status}）`, res.status)
    }

    if (!envelope || envelope.success !== true) {
      const e = envelope?.error || { code: 'UNKNOWN', message: `HTTP ${res.status}` }
      throw new ApiError(e.code, e.message, res.status)
    }
    return envelope.data
  } catch (err) {
    if (err.name === 'AbortError') {
      const e = new ApiError('TIMEOUT', '请求超时（8s），请检查网络', 0)
      if (!silent) toastError(e)
      throw e
    }
    if (!silent) toastError(err)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  get: (path, opts) => request(path, opts),
  post: (path, body, opts) => request(path, { method: 'POST', body, ...opts }),
}

export function getStoredApiKey() {
  return localStorage.getItem(KEY_STORAGE) || ''
}

export function setStoredApiKey(key) {
  if (key) localStorage.setItem(KEY_STORAGE, key.trim())
  else localStorage.removeItem(KEY_STORAGE)
}
