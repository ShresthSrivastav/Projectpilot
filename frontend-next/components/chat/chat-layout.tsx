"use client"

import { useEffect, useRef, useState, useCallback, useMemo } from "react"
import { useRouter } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { useConversations, useMessages } from "@/lib/hooks/use-chat"
import { chatApi } from "@/lib/api/chat"
import { ConversationSidebar } from "./conversation-sidebar"
import { ChatInput } from "./chat-input"
import { ChatMessage } from "./chat-message"
import { ThinkingIndicator } from "./thinking-indicator"
import { Sparkles, MessageSquare } from "lucide-react"
import { Card } from "@/components/ui/card"
import { toast } from "sonner"
import type { ChatMessage as ChatMessageType } from "@/lib/utils/types"

interface ChatLayoutProps {
  conversationId?: string
}

export function ChatLayout({ conversationId }: ChatLayoutProps) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { data: conversations } = useConversations()
  const { data: apiMessages, isLoading: msgsLoading } = useMessages(conversationId ?? null)
  const [localMessages, setLocalMessages] = useState<ChatMessageType[]>([])
  const [sending, setSending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const displayMessages = useMemo(
    () => conversationId ? (apiMessages ?? []) : localMessages,
    [conversationId, apiMessages, localMessages]
  )
  const isEmpty = displayMessages.length === 0

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [displayMessages, sending])

  const handleNew = useCallback(() => {
    setLocalMessages([])
    router.push("/chat")
  }, [router])

  const handleSend = useCallback(
    async (content: string) => {
      if (!conversationId) {
        setLocalMessages((prev) => [...prev, { role: "user", content }])
      }
      setSending(true)

      try {
        const data = await chatApi.send({
          message: content,
          conversation_id: conversationId,
        })

        if (conversationId) {
          queryClient.invalidateQueries({
            queryKey: ["conversation", conversationId, "messages"],
          })
        } else {
          setLocalMessages((prev) => [
            ...prev,
            { role: "assistant", content: data.response },
          ])
          if (data.conversation_id) {
            router.push(`/chat/${data.conversation_id}`)
          }
          queryClient.invalidateQueries({ queryKey: ["conversations"] })
        }
      } catch {
        const errMsg = { role: "assistant" as const, content: "*Failed to send message. Please try again.*" }
        if (!conversationId) {
          setLocalMessages((prev) => [...prev, errMsg])
        } else {
          toast.error("Failed to send message")
        }
      } finally {
        setSending(false)
      }
    },
    [conversationId, queryClient, router]
  )

  return (
    <div className="flex h-[calc(100dvh-4rem)]">
      <ConversationSidebar
        conversations={conversations}
        activeId={conversationId}
        onNew={handleNew}
      />

      <div className="flex flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-6" aria-live="polite" aria-atomic="false">
          <div className="mx-auto max-w-3xl space-y-4">
            {isEmpty ? (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 mb-4">
                  <Sparkles className="h-8 w-8 text-primary" />
                </div>
                <h2 className="text-lg font-semibold mb-1">How can I help you?</h2>
                <p className="text-sm text-muted-foreground max-w-sm">
                  Ask me about your projects, debug issues, or get help with generated code
                </p>
              </div>
            ) : (
              <>
                {msgsLoading && conversationId ? (
                  <div className="flex items-center justify-center py-8">
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <MessageSquare className="h-4 w-4 animate-pulse" />
                      <span className="text-sm">Loading messages...</span>
                    </div>
                  </div>
                ) : (
                  displayMessages.map((msg, i) => (
                    <ChatMessage
                      key={msg.timestamp || `${msg.role}-${i}`}
                      message={msg}
                      isLast={i === displayMessages.length - 1}
                    />
                  ))
                )}
              </>
            )}

            {sending && <ThinkingIndicator />}

            <div ref={endRef} />
          </div>
        </div>

        <div className="border-t border-border px-4 py-3">
          <div className="mx-auto max-w-3xl">
            <Card className="p-2">
              <ChatInput onSend={handleSend} isLoading={sending} />
            </Card>
            <p className="text-[10px] text-muted-foreground/40 text-center mt-1.5">
              AI may produce inaccurate information. Messages are saved to your conversation history.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
