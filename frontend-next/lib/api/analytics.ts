import { apiGet } from "./client"

export const analyticsApi = {
  overview: () => apiGet<Record<string, unknown>>("/analytics/overview"),
  projects: () => apiGet<Record<string, unknown>[]>("/analytics/projects"),
  projectDetail: (jobId: string) => apiGet<Record<string, unknown>>(`/analytics/project/${jobId}`),
}
