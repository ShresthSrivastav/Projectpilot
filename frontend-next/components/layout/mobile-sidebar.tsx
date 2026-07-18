"use client"

import { useEffect, useRef } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils/cn"
import { useUIStore } from "@/lib/stores/ui-store"
import { Button } from "@/components/ui/button"
import { PanelRightOpen, X } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

const navItems = [
  { href: "/generate", label: "Generate", icon: "Sparkles" },
  { href: "/history", label: "History", icon: "Clock" },
  { href: "/chat", label: "Chat", icon: "MessageSquare" },
  { separator: true },
  { href: "/workspace", label: "Workspace", icon: "Users" },
  { href: "/ecosystem", label: "Ecosystem", icon: "Puzzle" },
  { separator: true },
  { href: "/analytics", label: "Analytics", icon: "BarChart3" },
  { href: "/evaluation", label: "Evaluation", icon: "ClipboardCheck" },
  { href: "/organization", label: "Organization", icon: "Building2" },
  { separator: true },
  { href: "/settings", label: "Settings", icon: "Settings" },
]

// Lazy load icons
import {
  Sparkles, Clock, MessageSquare,
  Users, BarChart3, ClipboardCheck,
  Building2, Puzzle, Settings,
} from "lucide-react"

const iconMap: Record<string, React.ElementType> = {
  Sparkles, Clock, MessageSquare,
  Users, BarChart3, ClipboardCheck,
  Building2, Puzzle, Settings,
}

export function MobileSidebar() {
  const pathname = usePathname()
  const { sidebarOpen, setSidebarOpen } = useUIStore()
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSidebarOpen(false)
    }
    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [setSidebarOpen])

  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname, setSidebarOpen])

  return (
    <>
      {/* Overlay */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* Drawer */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            ref={ref}
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ type: "spring", damping: 25, stiffness: 250 }}
            className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-card"
            role="navigation"
            aria-label="Mobile navigation"
          >
            <div className="flex h-14 items-center justify-between border-b border-border px-4">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
                  <PanelRightOpen className="h-4 w-4 text-primary-foreground" />
                </div>
                <span className="font-semibold text-sm">ProjectPilot</span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setSidebarOpen(false)}
                aria-label="Close navigation menu"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
              {navItems.map((item, i) => {
                if ("separator" in item) {
                  return <div key={i} className="my-2 h-px bg-border" />
                }
                const Icon = iconMap[item.icon]
                const active = pathname.startsWith(item.href)
                return (
                  <Link key={item.href} href={item.href}>
                    <Button
                      variant="ghost"
                      className={cn(
                        "w-full justify-start gap-3 px-3 font-normal",
                        active
                          ? "bg-primary/10 text-primary hover:bg-primary/15"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      aria-current={active ? "page" : undefined}
                    >
                      {Icon && <Icon className="h-4 w-4 shrink-0" />}
                      <span>{item.label}</span>
                    </Button>
                  </Link>
                )
              })}
            </nav>
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  )
}
