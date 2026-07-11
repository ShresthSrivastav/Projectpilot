import { apiGet, apiPost } from "./client"
import type { BenchmarkResult } from "@/lib/utils/types"

export const benchmarksApi = {
  domains: () => apiGet<string[]>("/benchmarks/domains"),

  run: (data: { domain: string; model?: string; iteration?: number }) =>
    apiPost<{ run_id: string }>("/benchmarks/run", data),

  results: (params?: { domain?: string; limit?: number }) =>
    apiGet<BenchmarkResult[]>("/benchmarks/results", params as Record<string, unknown>),

  result: (runId: string) =>
    apiGet<BenchmarkResult>(`/benchmarks/result/${runId}`),

  leaderboard: (params?: { domain?: string; limit?: number }) =>
    apiGet<BenchmarkResult[]>("/benchmarks/leaderboard", params as Record<string, unknown>),

  compare: (runId1: string, runId2: string) =>
    apiPost<Record<string, unknown>>("/benchmarks/compare", { run_id_1: runId1, run_id_2: runId2 }),

  report: (runId: string, format = "json") =>
    apiGet<Record<string, unknown>>(`/benchmarks/report/${runId}?format=${format}`),

  trends: (params?: { domain?: string }) =>
    apiGet<Record<string, unknown>[]>("/benchmarks/trends", params as Record<string, unknown>),

  statistics: () => apiGet<Record<string, unknown>>("/benchmarks/statistics"),
}
