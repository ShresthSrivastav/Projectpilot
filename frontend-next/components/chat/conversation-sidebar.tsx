"use client"

import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Plus, MessageSquare, Search } from "lucide-react"
import { useState } from "react"
import { cn } from "@/lib/utils/cn"
import { formatRelativeTime } from "@/lib/utils/formatters"
import type { Conversation } from "@/lib/utils/types"

interface ConversationSidebarProps {
  conversations: Conversation[] | undefined
  activeId?: string
  onNew: () => void
  className?: string
}

export function ConversationSidebar({
  conversations,
  activeId,
  onNew,
  className,
}: ConversationSidebarProps) {
  const router = useRouter()
  const [search, setSearch] = useState("")

  const filtered = conversations?.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={cn("flex w-64 shrink-0 hidden md:block flex-col border-r border-border", className)}>
      {/* Header + new button */}
      <div className="p-3 space-y-3">
        <Button size="sm" className="w-full justify-start" onClick={onNew}>
          <Plus className="mr-2 h-4 w-4" /> New Chat
        </Button>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search conversations..."
            className="w-full h-8 rounded-md border border-border bg-transparent pl-8 pr-3 text-xs placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <Separator />
      </div>

      {/* Conversations list */}
      <ScrollArea className="flex-1">
        <div className="space-y-0.5 px-2 pb-2">
          {!filtered || filtered.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-center px-3">
              <MessageSquare className="h-6 w-6 text-muted-foreground mb-2 opacity-40" />
              <p className="text-xs text-muted-foreground">
                {search ? "No matching conversations" : "No conversations yet"}
              </p>
            </div>
          ) : (
            filtered.map((conv) => {
              const isActive = conv.id === activeId
              return (
                <button
                  key={conv.id}
                  onClick={() => router.push(`/chat/${conv.id}`)}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left text-xs transition-colors group",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <MessageSquare className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{conv.title}</p>
                    <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                      {conv.updated_at ? formatRelativeTime(conv.updated_at) : ""}
                    </p>
                  </div>
                </button>
              )
            })
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
