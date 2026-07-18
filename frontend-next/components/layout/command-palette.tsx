"use client"

import { useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { useUIStore } from "@/lib/stores/ui-store"
import { useHotkeys } from "@/lib/hooks/use-hotkeys"
import { Command } from "cmdk"
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
  Search,
  FileText,
} from "lucide-react"
import { useJobs } from "@/lib/hooks/use-job-polling"

const pages = [
  { id: "generate", label: "Generate Project", icon: Sparkles, href: "/generate" },
  { id: "history", label: "History", icon: Clock, href: "/history" },
  { id: "chat", label: "Chat", icon: MessageSquare, href: "/chat" },
  { id: "workspace", label: "Workspace", icon: Users, href: "/workspace" },
  { id: "ecosystem", label: "Ecosystem", icon: Puzzle, href: "/ecosystem" },
  { id: "analytics", label: "Analytics", icon: BarChart3, href: "/analytics" },
  { id: "evaluation", label: "Evaluation", icon: ClipboardCheck, href: "/evaluation" },
  { id: "org", label: "Organization", icon: Building2, href: "/organization" },
  { id: "settings", label: "Settings", icon: Settings, href: "/settings" },
]

export function CommandPalette() {
  const { commandPaletteOpen, setCommandPaletteOpen } = useUIStore()
  const router = useRouter()
  const { data: jobs } = useJobs()

  useHotkeys("Meta+K", () => setCommandPaletteOpen(true))
  useHotkeys("Ctrl+K", () => setCommandPaletteOpen(true))

  const handleSelect = useCallback(
    (id: string) => {
      setCommandPaletteOpen(false)
      if (id.startsWith("job-")) {
        router.push(`/history/${id.replace("job-", "")}`)
      } else {
        const page = pages.find((p) => p.id === id)
        if (page) router.push(page.href)
      }
    },
    [router, setCommandPaletteOpen]
  )

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "Escape" && commandPaletteOpen) {
        setCommandPaletteOpen(false)
      }
    }
    document.addEventListener("keydown", down)
    return () => document.removeEventListener("keydown", down)
  }, [commandPaletteOpen, setCommandPaletteOpen])

  if (!commandPaletteOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
      onClick={() => setCommandPaletteOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      aria-describedby="command-palette-instructions"
    >
      <div
        className="fixed left-[50%] top-[20%] z-50 w-full max-w-lg translate-x-[-50%] px-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
          <Command className="w-full" label="Command Menu">
            <div className="flex items-center border-b border-border px-3">
              <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
              <Command.Input
                placeholder="Search pages, projects..."
                className="flex h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                autoFocus
              />
            </div>

            <Command.List className="max-h-72 overflow-y-auto p-2">
              <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
                No results found.
              </Command.Empty>

              <Command.Group heading="Pages">
                {pages.map((page) => (
                  <Command.Item
                    key={page.id}
                    value={page.id}
                    onSelect={() => handleSelect(page.id)}
                    className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted"
                  >
                    <page.icon className="h-4 w-4 text-muted-foreground" />
                    <span>{page.label}</span>
                  </Command.Item>
                ))}
              </Command.Group>

              {jobs && jobs.length > 0 && (
                <Command.Group heading="Recent Projects">
                  {jobs.slice(0, 5).map((job) => (
                    <Command.Item
                      key={job.job_id}
                      value={`job-${job.job_id}`}
                      onSelect={() => handleSelect(`job-${job.job_id}`)}
                      className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 text-sm hover:bg-muted"
                    >
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span>{job.project_name ?? job.job_id}</span>
                      <span className="ml-auto text-xs text-muted-foreground">{job.status}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>

            <div id="command-palette-instructions" className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
              <span className="mr-4">↑↓ Navigate</span>
              <span className="mr-4">↵ Open</span>
              <span>Esc Close</span>
            </div>
          </Command>
        </div>
      </div>
    </div>
  )
}
