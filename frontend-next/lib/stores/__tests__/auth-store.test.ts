import { describe, it, expect, beforeEach } from "vitest"
import { useAuthStore } from "../auth-store"
import type { User, Workspace } from "@/lib/utils/types"

const mockUser: User = {
  id: "u1",
  name: "Alice",
  email: "alice@example.com",
  is_active: true,
  created_at: "2025-01-01T00:00:00Z",
  last_login: "2025-06-01T00:00:00Z",
}

const mockWorkspace: Workspace = {
  id: "w1",
  name: "My Workspace",
  owner_id: "u1",
  created_at: "2025-01-01T00:00:00Z",
}

beforeEach(() => {
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    workspace: null,
    isAuthenticated: false,
    isLoading: false,
  })
  localStorage.clear()
})

describe("auth store", () => {
  it("setAuth stores tokens, user, and sets isAuthenticated", () => {
    useAuthStore.getState().setAuth("access-123", "refresh-456", mockUser)
    const s = useAuthStore.getState()
    expect(s.accessToken).toBe("access-123")
    expect(s.refreshToken).toBe("refresh-456")
    expect(s.user).toEqual(mockUser)
    expect(s.isAuthenticated).toBe(true)
    expect(s.isLoading).toBe(false)
  })

  it("setAuth persists refreshToken to localStorage", () => {
    useAuthStore.getState().setAuth("a", "rt-value", mockUser)
    expect(localStorage.getItem("refreshToken")).toBe("rt-value")
  })

  it("logout clears all state and removes refreshToken from localStorage", () => {
    useAuthStore.getState().setAuth("a", "rt", mockUser)
    useAuthStore.getState().setWorkspace(mockWorkspace)
    useAuthStore.getState().logout()
    const s = useAuthStore.getState()
    expect(s.accessToken).toBeNull()
    expect(s.refreshToken).toBeNull()
    expect(s.user).toBeNull()
    expect(s.workspace).toBeNull()
    expect(s.isAuthenticated).toBe(false)
    expect(localStorage.getItem("refreshToken")).toBeNull()
  })

  it("setWorkspace updates the workspace", () => {
    useAuthStore.getState().setWorkspace(mockWorkspace)
    expect(useAuthStore.getState().workspace).toEqual(mockWorkspace)
  })

  it("setLoading updates isLoading", () => {
    useAuthStore.getState().setLoading(true)
    expect(useAuthStore.getState().isLoading).toBe(true)
    useAuthStore.getState().setLoading(false)
    expect(useAuthStore.getState().isLoading).toBe(false)
  })

  it("setTokens updates access and refresh tokens", () => {
    useAuthStore.getState().setTokens("new-access", "new-refresh")
    const s = useAuthStore.getState()
    expect(s.accessToken).toBe("new-access")
    expect(s.refreshToken).toBe("new-refresh")
  })
})
