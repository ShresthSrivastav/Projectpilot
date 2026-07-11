"use client"

import { useEffect, useRef } from "react"
import { useRouter } from "next/navigation"
import { useAuthStore } from "@/lib/stores/auth-store"
import { authApi } from "@/lib/api/auth"

export function useAuth() {
  const store = useAuthStore()
  const router = useRouter()
  const initialized = useRef(false)

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const initAuth = async () => {
      const refreshToken = localStorage.getItem("refreshToken")
      if (refreshToken && !store.isAuthenticated) {
        try {
          const data = await authApi.refresh(refreshToken)
          store.setAuth(data.access_token, data.refresh_token, data.user)
        } catch {
          localStorage.removeItem("refreshToken")
          store.setLoading(false)
        }
      } else {
        store.setLoading(false)
      }
    }
    initAuth()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (email: string, password: string) => {
    const data = await authApi.login({ email, password })
    store.setAuth(data.access_token, data.refresh_token, data.user)
    router.push("/dashboard")
  }

  const register = async (name: string, email: string, password: string) => {
    const data = await authApi.register({
      name,
      email,
      password,
      confirm_password: password,
    })
    store.setAuth(data.access_token, data.refresh_token, data.user)
    router.push("/dashboard")
  }

  const logout = async () => {
    try {
      if (store.refreshToken) await authApi.logout(store.refreshToken)
    } catch {
      // ignore server-side logout failure; clear local state regardless
    }
    store.logout()
    router.push("/login")
  }

  return { ...store, login, register, logout }
}
