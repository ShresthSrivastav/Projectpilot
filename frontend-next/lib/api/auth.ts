import { apiGet, apiPost, apiPublicPost } from "./client"
import type { AuthResponse, User } from "@/lib/utils/types"
import { API_BASE } from "@/lib/utils/constants"

export const authApi = {
  register: (data: { name: string; email: string; password: string; confirm_password: string }) =>
    apiPublicPost<AuthResponse>("/api/auth/register", data),

  login: (data: { email: string; password: string }) =>
    apiPublicPost<AuthResponse>("/api/auth/login", data),

  logout: (refreshToken: string) =>
    apiPost<{ message: string }>("/api/auth/logout", { refresh_token: refreshToken }),

  refresh: (refreshToken: string) =>
    apiPublicPost<AuthResponse>("/api/auth/refresh", { refresh_token: refreshToken }),

  me: () => apiGet<User>("/api/auth/me"),
}

export function authLoginUrl() {
  return `${API_BASE}/api/auth/login`
}

export function authRegisterUrl() {
  return `${API_BASE}/api/auth/register`
}
