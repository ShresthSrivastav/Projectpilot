"use client"

import { useTheme } from "next-themes"
import { useEffect, useState } from "react"

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => setMounted(true), [])

  if (!mounted) return null

  const isDark = theme === "dark"

  return (
    <button
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="chrome glass-pill px-3 py-1.5 cursor-pointer hover:bg-[var(--color-surface-glass-hover)] transition-colors duration-150"
      aria-label={`Switch to ${isDark ? "light" : "dark"} theme`}
    >
      THEME{" "}
      <span className="text-[var(--color-accent)]" aria-hidden="true">
        [{isDark ? "A" : "▣"}]
      </span>
    </button>
  )
}
