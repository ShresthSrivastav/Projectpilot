"use client"

import { useParams } from "next/navigation"
import { ChatLayout } from "@/components/chat/chat-layout"

export default function ConversationPage() {
  const params = useParams()
  return <ChatLayout conversationId={params.conversationId as string} />
}
