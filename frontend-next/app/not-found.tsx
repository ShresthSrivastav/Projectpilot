import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Home, Search } from "lucide-react"

export default function NotFound() {
  return (
    <div className="flex h-screen items-center justify-center bg-background p-4">
      <div className="flex flex-col items-center text-center max-w-md">
        <p className="text-6xl font-bold text-muted-foreground/20 mb-4">404</p>
        <h1 className="text-lg font-semibold mb-1">Page not found</h1>
        <p className="text-sm text-muted-foreground mb-6">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="flex gap-3">
          <Link href="/dashboard">
            <Button>
              <Home className="mr-1.5 h-4 w-4" /> Go home
            </Button>
          </Link>
          <Link href="/generate">
            <Button variant="outline">
              <Search className="mr-1.5 h-4 w-4" /> New project
            </Button>
          </Link>
        </div>
      </div>
    </div>
  )
}
