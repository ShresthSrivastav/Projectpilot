"use client"

import { create } from "zustand"
import type { User, Workspace } from "@/lib/utils/types"

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  workspace: Workspace | null
  isAuthenticated: boolean
  isLoading: boolean

  setAuth: (accessToken: string, refreshToken: string, user: User) => void
  setWorkspace: (workspace: Workspace) => void
  setLoading: (loading: boolean) => void
  setTokens: (accessToken: string, refreshToken: string) => void
  logout: () => void
}

function getStoredRefreshToken(): string | null {
  if (typeof window === "undefined") return null
  try {
    return localStorage.getItem("refreshToken")
  } catch {
    return null
  }
}

export const useAuthStore = create<AuthState>((set) => {
  const storedRefreshToken = getStoredRefreshToken()

  return {
    accessToken: null,
    refreshToken: storedRefreshToken,
    user: null,
    workspace: null,
    isAuthenticated: false,
    isLoading: true,

    setAuth: (accessToken, refreshToken, user) => {
      if (typeof window !== "undefined") {
        localStorage.setItem("refreshToken", refreshToken)
      }
      set({ accessToken, refreshToken, user, isAuthenticated: true, isLoading: false })
    },

    setWorkspace: (workspace) => set({ workspace }),

    setLoading: (loading) => set({ isLoading: loading }),

    setTokens: (accessToken, refreshToken) => {
      if (typeof window !== "undefined") {
        localStorage.setItem("refreshToken", refreshToken)
      }
      set({ accessToken, refreshToken })
    },

    logout: () => {
      if (typeof window !== "undefined") {
        localStorage.removeItem("refreshToken")
      }
      set({
        accessToken: null,
        refreshToken: null,
        user: null,
        workspace: null,
        isAuthenticated: false,
        isLoading: false,
      })
    },
  }
})
