import { apiGet } from "./client"
import type { DashboardData } from "@/lib/utils/types"
import { WS_BASE } from "@/lib/utils/constants"

export const dashboardApi = {
  status: () => apiGet<DashboardData>("/dashboard/status"),
  timeline: (limit = 100) => apiGet<Record<string, unknown>[]>(`/dashboard/timeline?limit=${limit}`),
  agents: () => apiGet<Record<string, unknown>[]>("/dashboard/agents"),
  memory: () => apiGet<Record<string, unknown>>("/dashboard/memory"),
}

export function createDashboardWebSocket(token: string): WebSocket {
  return new WebSocket(`${WS_BASE}/dashboard/stream?token=${token}`)
}
