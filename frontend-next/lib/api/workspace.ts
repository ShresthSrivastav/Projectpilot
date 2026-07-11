import { apiGet, apiPost, apiDelete } from "./client"
import type { Workspace, WorkspaceMember, Activity, Notification } from "@/lib/utils/types"

export const workspaceApi = {
  current: () => apiGet<Workspace>("/api/workspace/current"),

  list: () => apiGet<Workspace[]>("/api/workspace"),

  create: (data: { name: string }) =>
    apiPost<Workspace>("/api/workspace", data),

  switch: (workspaceId: string) =>
    apiPost<{ access_token: string }>("/api/workspace/switch", { workspace_id: workspaceId }),

  members: () => apiGet<WorkspaceMember[]>("/api/workspace/current/members"),

  invite: (data: { email: string; role: string }) =>
    apiPost<{ message: string }>("/api/workspace/current/invite", data),

  removeMember: (memberId: string) =>
    apiDelete<{ message: string }>(`/api/workspace/current/members/${memberId}`),

  invites: () => apiGet<{ id: string; email: string; role: string }[]>("/api/workspace/current/invites"),

  acceptInvite: (token: string) =>
    apiPost<{ message: string }>("/api/workspace/accept", { token }),

  activity: (limit = 50) =>
    apiGet<Activity[]>(`/api/workspace/current/activity?limit=${limit}`),

  notifications: (unreadOnly = false, limit = 20) =>
    apiGet<Notification[]>(`/api/workspace/notifications?unread_only=${unreadOnly}&limit=${limit}`),

  markRead: (notificationId: string) =>
    apiPost<{ message: string }>("/api/workspace/notifications/mark-read", { notification_id: notificationId }),

  markAllRead: () =>
    apiPost<{ message: string }>("/api/workspace/notifications/mark-all-read"),
}
