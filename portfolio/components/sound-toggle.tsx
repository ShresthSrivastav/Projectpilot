"use client"

import { useEffect, useState } from "react"

type SoundState = "on" | "off"

export function SoundToggle() {
  const [sound, setSound] = useState<SoundState>("off")

  useEffect(() => {
    const stored = localStorage.getItem("portfolio-sound")
    if (stored === "on" || stored === "off") setSound(stored)
  }, [])

  const toggle = () => {
    const next: SoundState = sound === "on" ? "off" : "on"
    setSound(next)
    localStorage.setItem("portfolio-sound", next)
  }

  return (
    <button
      onClick={toggle}
      className="chrome glass-pill px-3 py-1.5 cursor-pointer hover:bg-[var(--color-surface-glass-hover)] transition-colors duration-150"
      aria-label={`Sound ${sound === "on" ? "on" : "off"}`}
    >
      SOUND{" "}
      <span className="text-[var(--color-accent)]" aria-hidden="true">
        [{sound === "on" ? "♪" : "|"}]
      </span>
    </button>
  )
}
