import { apiGet, apiPost, apiDelete, apiDownload } from "./client"
import type {
  JobStatus,
  GenerateResponse,
  ClarifyResponse,
  ReviewResponse,
  GenerateRequest,
} from "@/lib/utils/types"

export const pipelineApi = {
  clarify: (data: { prompt: string; model?: string }) =>
    apiPost<ClarifyResponse>("/clarify", data),

  generate: (data: GenerateRequest) =>
    apiPost<GenerateResponse>("/generate-project", data),

  status: (jobId: string) =>
    apiGet<JobStatus>(`/status/${jobId}`),

  files: (jobId: string) =>
    apiGet<string[]>(`/files/${jobId}`),

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

  changelog: (jobId: string) =>
    apiGet<string>(`/changelog/${jobId}`),

  download: (jobId: string) =>
    apiDownload(`/download/${jobId}`),

  jobs: () =>
    apiGet<JobStatus[]>("/jobs"),

  delete: (jobId: string) =>
    apiDelete<{ message: string }>(`/jobs/${jobId}`),
}
