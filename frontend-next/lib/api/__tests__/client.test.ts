import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { apiGet, apiPost, apiPublicPost, ApiError, AuthError } from "../client"
import { useAuthStore } from "@/lib/stores/auth-store"
import type { User } from "@/lib/utils/types"

const mockFetch = vi.fn()
global.fetch = mockFetch

const testUser: User = {
  id: "1",
  name: "Test",
  email: "test@test.com",
  is_active: true,
  created_at: "",
  last_login: "",
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    workspace: null,
    isAuthenticated: false,
    isLoading: false,
  })
})

function okResponse(data: unknown) {
  return {
    ok: true,
    status: 200,
    text: () => Promise.resolve(JSON.stringify(data)),
    json: () => Promise.resolve(data),
  }
}

function errorResponse(status: number, data: unknown) {
  return {
    ok: false,
    status,
    text: () => Promise.resolve(JSON.stringify(data)),
    json: () => Promise.resolve(data),
  }
}

describe("apiGet", () => {
  it("sends a GET request and returns parsed data", async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ id: 1 }))
    const result = await apiGet<{ id: number }>("/items")
    expect(result).toEqual({ id: 1 })
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:5000/items",
      expect.objectContaining({ method: "GET" })
    )
  })

  it("appends query parameters to the URL", async () => {
    mockFetch.mockResolvedValueOnce(okResponse([]))
    await apiGet("/search", { q: "hello", page: 1 })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toBe("http://localhost:5000/search?q=hello&page=1")
  })

  it("skips null or undefined params", async () => {
    mockFetch.mockResolvedValueOnce(okResponse([]))
    await apiGet("/search", { a: "1", b: undefined, c: null })
    const url: string = mockFetch.mock.calls[0][0]
    expect(url).toBe("http://localhost:5000/search?a=1")
  })

  it("includes Authorization header when token is set", async () => {
    useAuthStore.getState().setAuth("my-token", "rt", testUser)
    mockFetch.mockResolvedValueOnce(okResponse({}))
    await apiGet("/secure")
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer my-token" }),
      })
    )
  })
})

describe("apiPost", () => {
  it("sends a POST request with JSON body", async () => {
    mockFetch.mockResolvedValueOnce(okResponse({ success: true }))
    const result = await apiPost("/create", { name: "foo" })
    expect(result).toEqual({ success: true })
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:5000/create",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "foo" }),
      })
    )
  })

  it("sends a POST request without body", async () => {
    mockFetch.mockResolvedValueOnce(okResponse({}))
    await apiPost("/no-body")
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
      })
    )
    const [, opts] = mockFetch.mock.calls[0]
    expect(opts.body).toBeUndefined()
  })
})

describe("apiPublicPost", () => {
  it("does not attach auth or recursively refresh on a 401", async () => {
    useAuthStore.getState().setAuth("stale-access", "stale-refresh", testUser)
    mockFetch.mockResolvedValueOnce(errorResponse(401, { detail: "Invalid email or password" }))

    await expect(apiPublicPost("/api/auth/login", { email: "x@y.z", password: "bad" }))
      .rejects.toThrow("Invalid email or password")

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [, options] = mockFetch.mock.calls[0]
    expect(options.headers).toEqual({ "Content-Type": "application/json" })
  })
})

describe("retry logic", () => {
  beforeEach(() => {
    vi.spyOn(global, "setTimeout").mockImplementation(((fn: VoidFunction) => {
      fn()
      return undefined as unknown as number
    }) as typeof global.setTimeout)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("retries on 503 and succeeds on second attempt", async () => {
    mockFetch
      .mockResolvedValueOnce(errorResponse(503, {}))
      .mockResolvedValueOnce(okResponse({ ok: true }))
    const result = await apiGet("/retry")
    expect(result).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it("retries on 429 (rate limited)", async () => {
    mockFetch
      .mockResolvedValueOnce(errorResponse(429, {}))
      .mockResolvedValueOnce(okResponse({ ok: true }))
    const result = await apiGet("/rate-limited")
    expect(result).toEqual({ ok: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it("throws ApiError after exhausting retries", async () => {
    mockFetch.mockResolvedValue(errorResponse(503, { message: "down" }))
    await expect(apiGet("/fail")).rejects.toThrow(ApiError)
    expect(mockFetch).toHaveBeenCalledTimes(3)
  })
})

describe("401 token refresh", () => {
  it("refreshes token and retries the original request", async () => {
    useAuthStore.getState().setAuth("old-token", "refresh-token-abc", testUser)
    mockFetch
      .mockResolvedValueOnce(errorResponse(401, {}))
      .mockResolvedValueOnce(
        okResponse({
          access_token: "new-token",
          refresh_token: "new-refresh",
          user: testUser,
        })
      )
      .mockResolvedValueOnce(okResponse({ data: "protected" }))
    const result = await apiGet("/protected")
    expect(result).toEqual({ data: "protected" })
    expect(useAuthStore.getState().accessToken).toBe("new-token")
  })

  it("throws AuthError when no refresh token is available", async () => {
    mockFetch.mockResolvedValueOnce(errorResponse(401, {}))
    await expect(apiGet("/protected")).rejects.toThrow(AuthError)
  })

  it("throws AuthError when refresh attempt fails", async () => {
    useAuthStore.getState().setAuth("old-token", "refresh-token-abc", testUser)
    mockFetch
      .mockResolvedValueOnce(errorResponse(401, {}))
      .mockResolvedValueOnce(errorResponse(400, {}))
    await expect(apiGet("/protected")).rejects.toThrow(AuthError)
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it("shares one rotating refresh request across concurrent 401 responses", async () => {
    useAuthStore.getState().setAuth("old-token", "refresh-token-abc", testUser)
    mockFetch
      .mockResolvedValueOnce(errorResponse(401, {}))
      .mockResolvedValueOnce(errorResponse(401, {}))
      .mockResolvedValueOnce(
        okResponse({
          access_token: "new-token",
          refresh_token: "new-refresh",
          user: testUser,
        })
      )
      .mockResolvedValueOnce(okResponse({ id: 1 }))
      .mockResolvedValueOnce(okResponse({ id: 2 }))

    const results = await Promise.all([
      apiGet<{ id: number }>("/protected/one"),
      apiGet<{ id: number }>("/protected/two"),
    ])

    expect(results).toEqual([{ id: 1 }, { id: 2 }])
    const refreshCalls = mockFetch.mock.calls.filter(([url]) =>
      String(url).endsWith("/api/auth/refresh")
    )
    expect(refreshCalls).toHaveLength(1)
  })
})

describe("error handling", () => {
  it("throws ApiError on 500", async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(500, { error: "Internal error" })
    )
    await expect(apiGet("/error")).rejects.toThrow(ApiError)
  })

  it("throws ApiError on 404", async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(404, { message: "Not found" })
    )
    await expect(apiGet("/not-found")).rejects.toThrow(ApiError)
  })

  it("throws ApiError on network failure", async () => {
    mockFetch.mockRejectedValueOnce(new TypeError("Failed to fetch"))
    await expect(apiGet("/offline")).rejects.toThrow(ApiError)
  })

  it("ApiError contains status and data", async () => {
    mockFetch.mockResolvedValueOnce(
      errorResponse(400, { detail: "Bad request" })
    )
    try {
      await apiGet("/bad")
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(400)
      expect((e as ApiError).data).toEqual({ detail: "Bad request" })
      expect((e as ApiError).message).toBe("Bad request")
    }
  })
})
