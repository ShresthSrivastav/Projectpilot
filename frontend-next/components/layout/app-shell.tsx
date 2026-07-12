"use client"

import { Sidebar } from "./sidebar"
import { MobileSidebar } from "./mobile-sidebar"
import { TopNav } from "./top-nav"
import { CommandPalette } from "./command-palette"
import { SkipToContent } from "./skip-to-content"
import { useUIStore } from "@/lib/stores/ui-store"
import { cn } from "@/lib/utils/cn"
import { useMediaQuery } from "@/lib/hooks/use-media-query"

interface AppShellProps {
  children: React.ReactNode
}

export function AppShell({ children }: AppShellProps) {
  const { sidebarCollapsed } = useUIStore()
  const isMobile = useMediaQuery("(max-width: 768px)")

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <SkipToContent />
      {isMobile ? <MobileSidebar /> : <Sidebar />}
      <div
        className={cn(
          "flex flex-1 flex-col overflow-hidden transition-all duration-200",
          !isMobile && !sidebarCollapsed && "md:ml-0"
        )}
      >
        <TopNav />
        <main id="main-content" className="flex-1 overflow-auto p-4 md:p-6" tabIndex={-1}>
          {children}
        </main>
      </div>
      <CommandPalette />
    </div>
  )
}
