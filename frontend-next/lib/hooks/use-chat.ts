"use client"

import { useState, useCallback } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { chatApi } from "@/lib/api/chat"
import type { ChatMessage } from "@/lib/utils/types"

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => chatApi.conversations(),
  })
}

export function useMessages(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversation", conversationId, "messages"],
    queryFn: () => chatApi.messages(conversationId!),
    enabled: !!conversationId,
  })
}

export function useChat(initialConversationId?: string | null) {
  const [conversationId, setConversationId] = useState<string | null>(
    initialConversationId ?? null
  )
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [pendingConfirm, setPendingConfirm] = useState<{
    tool_name: string
    args: Record<string, string>
  } | null>(null)
  const queryClient = useQueryClient()

  const sendMutation = useMutation({
    mutationFn: (content: string) =>
      chatApi.send({ message: content, conversation_id: conversationId ?? undefined }),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ])
      if (!conversationId) {
        setConversationId(data.conversation_id)
        queryClient.invalidateQueries({ queryKey: ["conversations"] })
      }
      if (data.pending_confirm) setPendingConfirm(data.pending_confirm)
      queryClient.invalidateQueries({ queryKey: ["conversations"] })
    },
  })

  const sendMessage = useCallback(
    (content: string) => {
      setMessages((prev) => [...prev, { role: "user", content }])
      setIsLoading(true)
      sendMutation.mutate(content, {
        onError: () => {
          setMessages((prev) =>
            prev.map((m, i) =>
              i === prev.length - 1 && m.role === "user"
                ? { ...m, content: `${m.content}\n\n*Failed to send*` }
                : m
            )
          )
        },
        onSettled: () => setIsLoading(false),
      })
    },
    [sendMutation]
  )

  const confirmAction = useCallback(async () => {
    if (!pendingConfirm || !conversationId) return
    try {
      setIsLoading(true)
      const data = await chatApi.confirmAction({
        conversation_id: conversationId,
        tool_name: pendingConfirm.tool_name,
        args: pendingConfirm.args,
      })
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ])
      setPendingConfirm(null)
    } catch {
      toast.error("Failed to confirm action")
    } finally {
      setIsLoading(false)
    }
  }, [pendingConfirm, conversationId])

  const createConversation = useCallback(() => {
    setConversationId(null)
    setMessages([])
    setPendingConfirm(null)
  }, [])

  return {
    conversationId,
    messages,
    isLoading,
    pendingConfirm,
    sendMessage,
    createConversation,
    setConversationId,
    setMessages,
    confirmAction,
    dismissConfirm: () => setPendingConfirm(null),
  }
}
