"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle, RotateCcw, LogOut } from "lucide-react"
import { useAuthStore } from "@/lib/stores/auth-store"
import { useRouter } from "next/navigation"

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  const logout = useAuthStore((s) => s.logout)
  const router = useRouter()

  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.error("Dashboard error:", error)
    }
  }, [error])

  return (
    <div className="flex h-full items-center justify-center p-4">
      <div className="flex flex-col items-center text-center max-w-md">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-error/10 mb-4">
          <AlertTriangle className="h-8 w-8 text-error" />
        </div>
        <h1 className="text-lg font-semibold mb-1">Dashboard error</h1>
        <p className="text-sm text-muted-foreground mb-6">
          Something went wrong loading this page.
        </p>
        <div className="flex gap-3">
          <Button onClick={reset}>
            <RotateCcw className="mr-1.5 h-4 w-4" /> Try again
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              logout()
              router.push("/login")
            }}
          >
            <LogOut className="mr-1.5 h-4 w-4" /> Log out
          </Button>
        </div>
      </div>
    </div>
  )
}
