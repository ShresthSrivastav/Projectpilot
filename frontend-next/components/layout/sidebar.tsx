"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils/cn"
import { useUIStore } from "@/lib/stores/ui-store"
import { Button } from "@/components/ui/button"
import {
  Sparkles,
  Clock,
  MessageSquare,
  Users,
  BarChart3,
  ClipboardCheck,
  Building2,
  Puzzle,
  Settings,
  ChevronLeft,
  ChevronRight,
  PanelRightOpen,
} from "lucide-react"

const navItems = [
  { href: "/generate", label: "Generate", icon: Sparkles },
  { href: "/history", label: "History", icon: Clock },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { separator: true },
  { href: "/workspace", label: "Workspace", icon: Users },
  { href: "/ecosystem", label: "Ecosystem", icon: Puzzle },
  { separator: true },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/evaluation", label: "Evaluation", icon: ClipboardCheck },
  { href: "/organization", label: "Organization", icon: Building2 },
  { separator: true },
  { href: "/settings", label: "Settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  const { sidebarCollapsed, setSidebarCollapsed } = useUIStore()

  return (
    <aside
      className={cn(
        "relative flex flex-col border-r border-border bg-card transition-all duration-200",
        sidebarCollapsed ? "w-14" : "w-56"
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-3">
        <div className={cn("flex items-center gap-2", sidebarCollapsed && "justify-center w-full")}>
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
            <PanelRightOpen className="h-4 w-4 text-primary-foreground" />
          </div>
          {!sidebarCollapsed && (
            <span className="font-semibold text-sm">ProjectPilot</span>
          )}
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 p-2">
        {navItems.map((item, i) => {
          if ("separator" in item) {
            return <div key={i} className="my-2 h-px bg-border" />
          }
          const Icon = item.icon
          const active = pathname.startsWith(item.href)
          return (
            <Link key={item.href} href={item.href} aria-label={sidebarCollapsed ? item.label : undefined}>
              <Button
                variant="ghost"
                size={sidebarCollapsed ? "icon" : "default"}
                className={cn(
                  "w-full justify-start gap-3 font-normal",
                  sidebarCollapsed ? "px-0 justify-center" : "px-3",
                  active
                    ? "bg-primary/10 text-primary hover:bg-primary/15"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!sidebarCollapsed && <span>{item.label}</span>}
              </Button>
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-border p-2">
          <Button
            variant="ghost"
            size={sidebarCollapsed ? "icon" : "default"}
            className="w-full justify-center text-muted-foreground hover:text-foreground"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : (
              <>
                <ChevronLeft className="h-4 w-4 mr-2" />
                <span className="text-xs">Collapse</span>
              </>
            )}
          </Button>
      </div>
    </aside>
  )
}
