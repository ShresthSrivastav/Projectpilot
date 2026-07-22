import { apiGet, apiPost, apiDelete } from "./client"
import type { Conversation, ChatMessage } from "@/lib/utils/types"

export const chatApi = {
  new: (data?: { conversation_id?: string; title?: string }) =>
    apiPost<{ conversation_id: string }>("/chat/new", data),

  send: (data: { message: string; conversation_id?: string; title?: string }) =>
    apiPost<{
      response: string
      conversation_id: string
      pending_confirm?: { tool_name: string; args: Record<string, string> }
    }>("/chat/send", data),

  confirmAction: (data: { conversation_id: string; tool_name: string; args: Record<string, string> }) =>
    apiPost<{ response: string }>("/chat/confirm-action", data),

  conversations: () =>
    apiGet<Conversation[]>("/chat/conversations"),

  messages: (id: string) =>
    apiGet<ChatMessage[]>(`/chat/conversations/${id}/messages`),

  delete: (id: string) =>
    apiDelete<{ message: string }>(`/chat/conversations/${id}`),
}
