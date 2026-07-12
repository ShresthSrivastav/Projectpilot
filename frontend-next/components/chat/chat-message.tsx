"use client"

import { memo } from "react"
import { cn } from "@/lib/utils/cn"
import { MarkdownRenderer } from "./markdown-renderer"
import { Bot, User } from "lucide-react"
import { formatRelativeTime } from "@/lib/utils/formatters"
import { motion } from "framer-motion"
import type { ChatMessage as ChatMessageType } from "@/lib/utils/types"

interface ChatMessageProps {
  message: ChatMessageType
  isLast?: boolean
}

export const ChatMessage = memo(function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user"

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn("flex items-start gap-3", isUser && "flex-row-reverse")}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground"
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5" />
        ) : (
          <Bot className="h-3.5 w-3.5" />
        )}
      </div>

      {/* Message content */}
      <div className={cn("flex flex-col", isUser ? "items-end" : "items-start", "max-w-[80%]")}>
        {/* Header */}
        <div className="flex items-center gap-2 mb-0.5 px-1">
          <span className="text-[11px] font-medium text-muted-foreground">
            {isUser ? "You" : "Assistant"}
          </span>
          {message.timestamp && (
            <span className="text-[10px] text-muted-foreground/50">
              {formatRelativeTime(message.timestamp)}
            </span>
          )}
        </div>

        {/* Bubble */}
        <div
          className={cn(
            "rounded-xl px-4 py-2.5",
            isUser
              ? "bg-primary text-primary-foreground"
              : "bg-muted/50 border border-border"
          )}
        >
          {isUser ? (
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>
      </div>
    </motion.div>
  )
})
