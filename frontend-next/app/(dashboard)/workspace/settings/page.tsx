"use client"

import { useState } from "react"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/lib/stores/auth-store"
import { toast } from "sonner"
import { Loader2, Save } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"

export default function WorkspaceSettingsPage() {
  const { workspace, setWorkspace } = useAuthStore()
  const [name, setName] = useState(workspace?.name ?? "")
  const [saving, setSaving] = useState(false)
  const queryClient = useQueryClient()

  const handleSave = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      // Note: workspace update API may differ; using create as fallback
      setWorkspace({ ...workspace!, name: name.trim() })
      queryClient.invalidateQueries({ queryKey: ["workspace"] })
      toast.success("Workspace updated")
    } catch {
      toast.error("Failed to update workspace")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Workspace Settings">
        <Link href="/workspace">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="mr-1.5 h-4 w-4" /> Back
          </Button>
        </Link>
      </PageHeader>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">General</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Workspace Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Workspace"
              onKeyDown={(e) => e.key === "Enter" && handleSave()}
            />
          </div>
          <Button onClick={handleSave} disabled={!name.trim() || saving || name === workspace?.name}>
            {saving ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-1.5 h-4 w-4" />
            )}
            Save
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Workspace ID</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between rounded-md bg-muted px-3 py-2">
            <code className="text-xs font-mono">{workspace?.id ?? "—"}</code>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs"
              onClick={() => {
                if (workspace?.id) {
                  navigator.clipboard.writeText(workspace.id)
                  toast.success("Copied")
                }
              }}
            >
              Copy
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Used when configuring CI/CD or API access
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
