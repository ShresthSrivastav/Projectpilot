import { apiGet, apiPost } from "./client"
import type { GitHubRepo, GitHubBranch, GitHubFile, GitHubPR, GitHubIssue } from "@/lib/utils/types"

export const githubApi = {
  connect: (data: { token: string; username: string }) =>
    apiPost<{ message: string }>("/github/connect", data),

  disconnect: (username: string) =>
    apiPost<{ message: string }>("/github/disconnect", { username }),

  connections: () => apiGet<{ username: string; connected_at: string }[]>("/github/connections"),

  repos: (username: string) =>
    apiGet<GitHubRepo[]>(`/github/${username}/repos`),

  branches: (fullName: string) =>
    apiGet<GitHubBranch[]>(`/github/${fullName}/branches`),

  createBranch: (fullName: string, data: { name: string; source_branch?: string }) =>
    apiPost<GitHubBranch>(`/github/${fullName}/branches`, data),

  files: (fullName: string, params?: { path?: string; ref?: string; username?: string }) =>
    apiGet<GitHubFile[]>(`/github/${fullName}/files`, params as Record<string, unknown>),

  getFile: (fullName: string, params: { path: string; ref?: string; username?: string }) =>
    apiGet<GitHubFile>(`/github/${fullName}/file`, params as Record<string, unknown>),

  saveFile: (fullName: string, data: { path: string; content: string; message: string; branch?: string }) =>
    apiPost<{ message: string }>(`/github/${fullName}/file`, data),

  pulls: (fullName: string, params?: { state?: string; username?: string }) =>
    apiGet<GitHubPR[]>(`/github/${fullName}/pulls`, params as Record<string, unknown>),

  createPR: (fullName: string, data: { title: string; body?: string; head: string; base: string }) =>
    apiPost<GitHubPR>(`/github/${fullName}/pulls`, data),

  issues: (fullName: string, params?: { state?: string; username?: string }) =>
    apiGet<GitHubIssue[]>(`/github/${fullName}/issues`, params as Record<string, unknown>),

  createIssue: (fullName: string, data: { title: string; body?: string }) =>
    apiPost<GitHubIssue>(`/github/${fullName}/issues`, data),
}
