"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { githubApi } from "@/lib/api/github"
import { toast } from "sonner"
import { useQueryClient } from "@tanstack/react-query"
import { GitBranch, Loader2 } from "lucide-react"

export function GitHubConnectDialog() {
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState("")
  const [username, setUsername] = useState("")
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const handleConnect = async () => {
    if (!token.trim() || !username.trim()) return
    setLoading(true)
    try {
      await githubApi.connect({ token: token.trim(), username: username.trim() })
      toast.success(`Connected as ${username}`)
      setToken("")
      setUsername("")
      setOpen(false)
      queryClient.invalidateQueries({ queryKey: ["github-connections"] })
    } catch {
      toast.error("Failed to connect GitHub")
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <GitBranch className="mr-1.5 h-4 w-4" /> Connect GitHub
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Connect GitHub Account</DialogTitle>
          <DialogDescription>
            Provide a GitHub personal access token with repo scope
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="username">GitHub Username</Label>
            <Input
              id="username"
              placeholder="octocat"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="token">Personal Access Token</Label>
            <Input
              id="token"
              type="password"
              placeholder="ghp_..."
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <p className="text-[10px] text-muted-foreground">
              Token needs repo, read:org scopes. Never shared.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleConnect} disabled={!token.trim() || !username.trim() || loading}>
            {loading && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
            Connect
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
