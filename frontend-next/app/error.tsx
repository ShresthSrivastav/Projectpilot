"use client"

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle, RotateCcw, Home } from "lucide-react"
import Link from "next/link"

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    if (process.env.NODE_ENV === "development") {
      console.error("Unhandled error:", error)
    }
  }, [error])

  return (
    <html>
      <body className="flex h-screen items-center justify-center bg-background p-4">
        <div className="flex flex-col items-center text-center max-w-md">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-error/10 mb-4">
            <AlertTriangle className="h-8 w-8 text-error" />
          </div>
          <h1 className="text-lg font-semibold mb-1">Something went wrong</h1>
          <p className="text-sm text-muted-foreground mb-6">
            An unexpected error occurred. Our team has been notified.
          </p>
          {error.digest && (
            <p className="text-[10px] font-mono text-muted-foreground/50 mb-4">
              Error ID: {error.digest}
            </p>
          )}
          <div className="flex gap-3">
            <Button onClick={reset}>
              <RotateCcw className="mr-1.5 h-4 w-4" /> Try again
            </Button>
            <Link href="/dashboard">
              <Button variant="outline">
                <Home className="mr-1.5 h-4 w-4" /> Go home
              </Button>
            </Link>
          </div>
        </div>
      </body>
    </html>
  )
}
