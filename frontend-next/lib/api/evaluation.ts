import { apiGet, apiPost } from "./client"

export const evaluationApi = {
  run: (data?: { trigger_type?: string }) =>
    apiPost<{ id: string }>("/evaluation/run", data),

  history: (params?: { limit?: number; trigger_type?: string; status?: string }) =>
    apiGet<Record<string, unknown>[]>("/evaluation/history", params as Record<string, unknown>),

  reports: (params?: { report_type?: string; limit?: number }) =>
    apiGet<Record<string, unknown>[]>("/evaluation/reports", params as Record<string, unknown>),

  leaderboards: (params?: { category?: string; sort_by?: string; limit?: number }) =>
    apiGet<Record<string, unknown>[]>("/evaluation/leaderboards", params as Record<string, unknown>),

  comparison: (params?: { from_version?: string; to_version?: string; limit?: number }) =>
    apiGet<Record<string, unknown>[]>("/evaluation/comparison", params as Record<string, unknown>),

  regressions: (params?: { category?: string; severity?: string; dismissed?: boolean; limit?: number }) =>
    apiGet<Record<string, unknown>[]>("/evaluation/regressions", params as Record<string, unknown>),
}
