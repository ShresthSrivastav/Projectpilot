"use client"

import { useEffect, useState } from "react"

function getTimeString(): string {
  const now = new Date()
  const time = now.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  })
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone
  const offset = -now.getTimezoneOffset()
  const sign = offset >= 0 ? "+" : "-"
  const hours = String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0")
  const abbrev = tz.split("/").pop() ?? tz
  return `${time} GMT${sign}${hours}`
}

export function HUD() {
  const [time, setTime] = useState(getTimeString)

  useEffect(() => {
    const id = setInterval(() => setTime(getTimeString()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="fixed bottom-6 right-6 z-50 hud-text select-none" aria-live="polite">
      {time}
    </div>
  )
}
