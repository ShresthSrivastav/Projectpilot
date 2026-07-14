"use client"

import { useEffect, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useAuthStore } from "@/lib/stores/auth-store"
import { authApi } from "@/lib/api/auth"

export function useAuth() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const isLoading = useAuthStore((s) => s.isLoading)
  const accessToken = useAuthStore((s) => s.accessToken)
  const refreshToken = useAuthStore((s) => s.refreshToken)
  const user = useAuthStore((s) => s.user)
  const workspace = useAuthStore((s) => s.workspace)
  const router = useRouter()
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const initAuth = async () => {
      const token = localStorage.getItem("refreshToken")
      if (!token || useAuthStore.getState().isAuthenticated) {
        useAuthStore.getState().setLoading(false)
        return
      }
      try {
        const data = await authApi.refresh(token)
        useAuthStore.getState().setAuth(data.access_token, data.refresh_token, data.user)
      } catch {
        localStorage.removeItem("refreshToken")
        useAuthStore.getState().setLoading(false)
      }
    }
    initAuth()
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login({ email, password })
    useAuthStore.getState().setAuth(data.access_token, data.refresh_token, data.user)
    router.replace("/dashboard")
  }, [router])

  const register = useCallback(async (name: string, email: string, password: string) => {
    const data = await authApi.register({
      name,
      email,
      password,
      confirm_password: password,
    })
    useAuthStore.getState().setAuth(data.access_token, data.refresh_token, data.user)
    router.replace("/dashboard")
  }, [router])

  const logout = useCallback(async () => {
    try {
      const rt = useAuthStore.getState().refreshToken
      if (rt) await authApi.logout(rt)
    } catch {
      // ignore server-side logout failure; clear local state regardless
    }
    useAuthStore.getState().logout()
    router.replace("/login")
  }, [router])

  return { isAuthenticated, isLoading, accessToken, refreshToken, user, workspace, login, register, logout }
}