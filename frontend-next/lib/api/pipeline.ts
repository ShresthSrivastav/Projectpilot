import { apiGet, apiPost, apiDelete, apiDownload } from "./client"
import type {
  JobStatus,
  GenerateResponse,
  ClarifyResponse,
  ReviewResponse,
  GenerateRequest,
} from "@/lib/utils/types"

function normalizeJobStatus(raw: Record<string, unknown>): JobStatus {
  return {
    ...raw,
    job_id: String(raw.job_id ?? ""),
    status: raw.status as JobStatus["status"],
    progress: Number(raw.progress ?? raw.progress_pct ?? 0),
    message: String(raw.message ?? raw.error_message ?? ""),
    project_name: raw.project_name as string | undefined,
    tests_total: Number(raw.tests_total ?? raw.test_total ?? 0),
    tests_passed: Number(raw.tests_passed ?? raw.test_passed ?? 0),
    tests_failed: Number(raw.tests_failed ?? raw.test_failed ?? 0),
    logs: Array.isArray(raw.logs) ? raw.logs.map(String) : [],
  }
}

export const pipelineApi = {
  clarify: (data: { prompt: string; model?: string }) =>
    apiPost<ClarifyResponse>("/clarify", data),

  generate: (data: GenerateRequest) =>
    apiPost<GenerateResponse>("/generate-project", data),

  status: async (jobId: string) =>
    normalizeJobStatus(await apiGet<Record<string, unknown>>(`/status/${jobId}`)),

  files: async (jobId: string) => {
    const data = await apiGet<string[] | { files?: unknown }>(`/files/${jobId}`)
    if (Array.isArray(data)) return data.map(String)
    return Array.isArray(data.files) ? data.files.map(String) : []
  },

  readFile: (jobId: string, filePath: string) =>
    apiGet<{ content: string }>(`/read-project-file/${jobId}/${encodeURIComponent(filePath)}`),

  cancel: (jobId: string) =>
    apiPost<{ message: string }>(`/cancel/${jobId}`),

  regenerate: (data: { job_id: string; file_path: string; correction_note?: string; model?: string }) =>
    apiPost<{ message: string }>("/regenerate-file", data),

  iterate: (jobId: string, data: { prompt: string; model?: string }) =>
    apiPost<{ job_id: string }>(`/iterate/${jobId}`, data),

  fixTests: (jobId: string, data: { model?: string }) =>
    apiPost<{ message: string }>(`/fix-tests/${jobId}`, data),

  review: (jobId: string, data: { model?: string }) =>
    apiPost<ReviewResponse>(`/review/${jobId}`, data),

  validate: (jobId: string) =>
    apiGet<Record<string, unknown>>(`/validate/${jobId}`),

  testFiles: (jobId: string) =>
    apiGet<Record<string, string>>(`/test-files/${jobId}`),

  changelog: async (jobId: string) => {
    const data = await apiGet<string | { changelog?: unknown }>(`/changelog/${jobId}`)
    return typeof data === "string" ? data : String(data.changelog ?? "")
  },

  download: (jobId: string) =>
    apiDownload(`/download/${jobId}`),

  jobs: async () =>
    (await apiGet<Record<string, unknown>[]>("/jobs")).map(normalizeJobStatus),

  delete: (jobId: string) =>
    apiDelete<{ message: string }>(`/jobs/${jobId}`),
}
