import { API_BASE } from "@/lib/utils/constants"
import { useAuthStore } from "@/lib/stores/auth-store"

const REQUEST_TIMEOUT = 15_000
const MAX_RETRIES = 2
const RETRYABLE_CODES = [408, 429, 502, 503, 504]

class AuthError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "AuthError"
  }
}

class ApiError extends Error {
  status: number
  data: unknown

  constructor(status: number, data: unknown) {
    const details = data && typeof data === "object" ? data as Record<string, unknown> : null
    const message = details && typeof details.detail === "string"
      ? details.detail
      : details && typeof details.message === "string"
        ? details.message
        : `API Error: ${status}`
    super(message)
    this.name = "ApiError"
    this.status = status
    this.data = data
  }
}

let refreshInFlight: Promise<boolean> | null = null

async function fetchWithTimeout(url: string, opts: RequestInit, timeoutMs = REQUEST_TIMEOUT): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, { ...opts, signal: controller.signal })
    return res
  } finally {
    clearTimeout(timer)
  }
}

async function performTokenRefresh(): Promise<boolean> {
  const refreshToken = useAuthStore.getState().refreshToken
  if (!refreshToken) return false

  try {
    const res = await fetchWithTimeout(
      `${API_BASE}/api/auth/refresh`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
      10_000
    )
    if (!res.ok) return false
    const data = await res.json()
    useAuthStore.getState().setAuth(data.access_token, data.refresh_token, data.user)
    return true
  } catch {
    return false
  }
}

async function attemptTokenRefresh(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performTokenRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

function getHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" }
  const token = useAuthStore.getState().accessToken
  if (token) headers["Authorization"] = `Bearer ${token}`
  return headers
}

function unwrapResponse(data: unknown): unknown {
  if (data === null || data === undefined || typeof data !== "object") return data
  if (Array.isArray(data)) return data

  const obj = data as Record<string, unknown>

  const knownEnvelopeKeys = [
    "results", "items", "data",
    "plugins", "packages", "agents", "workflows", "projects",
    "conversations", "messages",
    "repos", "branches", "files", "pull_requests", "issues",
    "runs", "events", "entries", "comparisons", "regressions",
    "reports", "connections", "organizations", "repositories", "changes",
    "members", "activity", "notifications", "invites",
    "leaderboard", "history",
    "jobs", "domains",
  ]

  for (const key of knownEnvelopeKeys) {
    if (Array.isArray(obj[key])) {
      return obj[key]
    }
  }

  return data
}

async function execFetch<T>(
  method: string,
  path: string,
  body?: unknown,
  retryCount = 0
): Promise<T> {
  const opts: RequestInit = { method, headers: getHeaders() }
  if (body) opts.body = JSON.stringify(body)

  try {
    const res = await fetchWithTimeout(`${API_BASE}${path}`, opts)

    if (res.status === 401) {
      const refreshed = await attemptTokenRefresh()
      if (refreshed) {
        opts.headers = getHeaders()
        const retryRes = await fetchWithTimeout(`${API_BASE}${path}`, opts)
        if (!retryRes.ok) {
          useAuthStore.getState().logout()
          throw new AuthError("Session expired")
        }
        const text = await retryRes.text()
        if (!text) return undefined as T
        return unwrapResponse(JSON.parse(text)) as T
      }
      useAuthStore.getState().logout()
      throw new AuthError("Session expired")
    }

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      if (retryCount < MAX_RETRIES && RETRYABLE_CODES.includes(res.status)) {
        await new Promise((r) => setTimeout(r, 1000 * (retryCount + 1)))
        return execFetch<T>(method, path, body, retryCount + 1)
      }
      throw new ApiError(res.status, data)
    }

    const text = await res.text()
    if (!text) return undefined as T
    return unwrapResponse(JSON.parse(text)) as T
  } catch (err) {
    if (err instanceof AuthError || err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, { message: "Request timed out" })
    }
    throw new ApiError(0, { message: "Network error", original: err instanceof Error ? err.message : String(err) })
  }
}

export function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(path, API_BASE)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v))
    })
  }
  return execFetch<T>("GET", url.pathname + url.search)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return execFetch<T>("POST", path, body)
}

export async function apiPublicPost<T>(path: string, body?: unknown, retryCount = 0): Promise<T> {
  const opts: RequestInit = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  }
  if (body) opts.body = JSON.stringify(body)

  try {
    const res = await fetchWithTimeout(`${API_BASE}${path}`, opts)
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      if (retryCount < MAX_RETRIES && RETRYABLE_CODES.includes(res.status)) {
        await new Promise((resolve) => setTimeout(resolve, 1000 * (retryCount + 1)))
        return apiPublicPost<T>(path, body, retryCount + 1)
      }
      throw new ApiError(res.status, data)
    }

    const text = await res.text()
    if (!text) return undefined as T
    return unwrapResponse(JSON.parse(text)) as T
  } catch (err) {
    if (err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, { message: "Request timed out" })
    }
    throw new ApiError(0, { message: "Network error", original: err instanceof Error ? err.message : String(err) })
  }
}

export function apiDelete<T>(path: string): Promise<T> {
  return execFetch<T>("DELETE", path)
}

async function execDownload(path: string, retryCount = 0): Promise<Blob> {
  const res = await fetchWithTimeout(`${API_BASE}${path}`, { headers: getHeaders() }, 30_000)

  if (res.status === 401) {
    const refreshed = await attemptTokenRefresh()
    if (refreshed) {
      const retryRes = await fetchWithTimeout(`${API_BASE}${path}`, { headers: getHeaders() }, 30_000)
      if (!retryRes.ok) {
        useAuthStore.getState().logout()
        throw new AuthError("Session expired")
      }
      return retryRes.blob()
    }
    useAuthStore.getState().logout()
    throw new AuthError("Session expired")
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    if (retryCount < MAX_RETRIES && RETRYABLE_CODES.includes(res.status)) {
      await new Promise((r) => setTimeout(r, 1000 * (retryCount + 1)))
      return execDownload(path, retryCount + 1)
    }
    throw new ApiError(res.status, data)
  }

  return res.blob()
}

export async function apiDownload(path: string): Promise<Blob> {
  try {
    return await execDownload(path)
  } catch (err) {
    if (err instanceof AuthError || err instanceof ApiError) throw err
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, { message: "Download timed out" })
    }
    throw new ApiError(0, { message: "Download failed", original: err instanceof Error ? err.message : String(err) })
  }
}

export { AuthError, ApiError }
