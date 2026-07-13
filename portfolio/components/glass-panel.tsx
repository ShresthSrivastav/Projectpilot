"use client"

import type { ReactNode } from "react"

export function GlassPanel({
  children,
  className = "",
  as = "div",
}: {
  children: ReactNode
  className?: string
  as?: "div" | "span"
}) {
  const Tag = as
  return <Tag className={`glass-card ${className}`}>{children}</Tag>
}
