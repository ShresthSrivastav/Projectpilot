"use client"

import { useState, useEffect, useRef } from "react"
import type { DashboardData } from "@/lib/utils/types"
import { createDashboardWebSocket } from "@/lib/api/dashboard"
import { useAuthStore } from "@/lib/stores/auth-store"

interface DashboardEvent {
  type: string
  data: unknown
  timestamp: string
}

export function useDashboardStream() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [events, setEvents] = useState<DashboardEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const token = useAuthStore.getState().accessToken
    if (!token) return

    const ws = createDashboardWebSocket(token)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === "initial") {
          setData(msg.data)
        } else {
          setEvents((prev) => [msg, ...prev].slice(0, 100))
        }
      } catch (err) {
        console.error("Failed to parse dashboard event:", err)
      }
    }

    const ping = setInterval(() => {
      if (ws.readyState !== WebSocket.OPEN) return
      try { ws.send("ping") } catch { /* connection lost */ }
    }, 30000)

    return () => {
      clearInterval(ping)
      ws.close()
    }
  }, [])

  return { data, events, connected }
}
