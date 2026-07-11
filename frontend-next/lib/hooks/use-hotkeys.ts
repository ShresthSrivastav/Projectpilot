"use client"

import { useEffect } from "react"

export function useHotkeys(key: string, callback: () => void, enabled = true) {
  useEffect(() => {
    if (!enabled) return

    const handler = (e: KeyboardEvent) => {
      const parts = key.split("+")
      const hasMeta = parts.includes("Meta") || parts.includes("Cmd")
      const hasCtrl = parts.includes("Ctrl")
      const hasShift = parts.includes("Shift")
      const targetKey = parts[parts.length - 1]

      const metaDown = e.metaKey || e.ctrlKey
      if (hasMeta && !metaDown) return
      if (!hasMeta && hasCtrl && !e.ctrlKey) return
      if (hasShift && !e.shiftKey) return
      if (e.key.toLowerCase() !== targetKey.toLowerCase()) return

      e.preventDefault()
      callback()
    }

    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [key, callback, enabled])
}
