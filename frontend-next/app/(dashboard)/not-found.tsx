import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Home } from "lucide-react"

export default function DashboardNotFound() {
  return (
    <div className="flex h-full items-center justify-center p-4">
      <div className="flex flex-col items-center text-center max-w-md">
        <p className="text-6xl font-bold text-muted-foreground/20 mb-4">404</p>
        <h1 className="text-lg font-semibold mb-1">Page not found</h1>
        <p className="text-sm text-muted-foreground mb-6">
           This section does not exist.
        </p>
        <Link href="/dashboard">
          <Button>
            <Home className="mr-1.5 h-4 w-4" /> Go to dashboard
          </Button>
        </Link>
      </div>
    </div>
  )
}
