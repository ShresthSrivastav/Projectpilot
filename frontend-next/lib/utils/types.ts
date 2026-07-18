export interface User {
  id: string
  name: string
  email: string
  is_active: boolean
  created_at: string
  last_login: string
}

export interface Workspace {
  id: string
  name: string
  owner_id: string
  created_at: string
}

export interface WorkspaceMember {
  id: string
  user_id: string
  name: string
  email: string
  role: "OWNER" | "ADMIN" | "MEMBER" | "VIEWER"
  joined_at: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface JobStatus {
  job_id: string
  status: "queued" | "running" | "complete" | "partial" | "failed" | "cancelled"
  progress: number
  message: string
  project_name?: string
  tests_total?: number
  tests_passed?: number
  tests_failed?: number
  logs?: string[]
  agents?: AgentStatus[]
  review_summary?: string
}

export interface AgentStatus {
  name: string
  status: "pending" | "running" | "complete" | "failed"
  duration?: number
}

export interface FileTree {
  [path: string]: string
}

export interface GenerateRequest {
  prompt: string
  project_name: string
  model?: string
  stack?: Record<string, string>
  clarification?: string
}

export interface ChatMessage {
  role: "user" | "assistant" | "system"
  content: string
  timestamp?: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ClarifyResponse {
  question: string | null
  prompt: string
}

export interface BenchmarkResult {
  run_id: string
  domain: string
  score: number
  metrics: Record<string, number>
  status: string
  created_at: string
}

export interface EvaluationRun {
  id: string
  status: string
  autonomy_score: number
  cost: number
  runtime: number
  success_rate: number
  created_at: string
}

export interface DashboardData {
  total_projects: number
  active_jobs: number
  total_files: number
  total_tokens: number
  avg_duration: number
  cpu_usage: number
  memory_usage: number
  gpu_usage: number
}

export interface GenerateResponse {
  job_id: string
  status: string
  message: string
}

export interface ReviewResponse {
  issues: ReviewIssue[]
  summary: string
  score: number
  error?: string
}

export interface ReviewIssue {
  severity: "error" | "warning" | "info"
  message: string
  file?: string
  line?: number
}

export interface Plugin {
  id: string
  name: string
  description: string
  version: string
  enabled: boolean
  plugin_type: string
}

export interface MarketplacePackage {
  id: string
  name: string
  description: string
  version: string
  author: string
  downloads: number
  rating: number
  package_type: string
}

export interface Organization {
  id: string
  name: string
  description?: string
  created_at: string
}

export interface Activity {
  id: string
  type: string
  description: string
  user_id: string
  user_name: string
  created_at: string
}

export interface Notification {
  id: string
  title: string
  message: string
  read: boolean
  created_at: string
}

export interface GitHubRepo {
  name: string
  full_name: string
  description: string
  html_url: string
  language: string
  updated_at: string
}

export interface GitHubBranch {
  name: string
  commit: { sha: string }
}

export interface GitHubFile {
  name: string
  path: string
  type: "file" | "dir"
  content?: string
}

export interface GitHubPR {
  number: number
  title: string
  state: string
  created_at: string
  user: { login: string }
}

export interface GitHubIssue {
  number: number
  title: string
  state: string
  created_at: string
}
