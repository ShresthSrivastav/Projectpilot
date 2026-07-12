import { apiGet, apiPost, apiDelete } from "./client"
import type { Organization } from "@/lib/utils/types"

export const organizationApi = {
  list: () => apiGet<Organization[]>("/organization/list"),

  create: (data: { name: string; description?: string }) =>
    apiPost<Organization>("/organization/create", data),

  addRepo: (data: { org_id: string; name: string; path: string }) =>
    apiPost<{ message: string }>("/organization/add-repo", data),

  index: (data: { org_id: string; model?: string }) =>
    apiPost<{ message: string }>("/organization/index", data),

  graph: (orgId: string) =>
    apiGet<string>(`/organization/graph?org_id=${orgId}`),

  repositories: (orgId: string) =>
    apiGet<Record<string, unknown>[]>(`/organization/repositories?org_id=${orgId}`),

  health: (orgId: string) =>
    apiGet<Record<string, unknown>>(`/organization/health?org_id=${orgId}`),

  impact: (data: { org_id: string; query: string }) =>
    apiPost<Record<string, unknown>>("/organization/impact", data),

  modify: (data: { org_id: string; description: string; changes: unknown[] }) =>
    apiPost<{ message: string }>("/organization/modify", data),

  report: (orgId: string) =>
    apiGet<Record<string, unknown>[]>(`/organization/report?org_id=${orgId}`),

  changes: (orgId: string) =>
    apiGet<Record<string, unknown>[]>(`/organization/changes?org_id=${orgId}`),

  validate: (data: { org_id: string; validation_types?: string[] }) =>
    apiPost<Record<string, unknown>>("/organization/validate", data),

  delete: (orgId: string) =>
    apiDelete<{ message: string }>(`/organization/${orgId}`),
}
