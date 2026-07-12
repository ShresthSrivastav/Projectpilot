"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { workspaceApi } from "@/lib/api/workspace"
import { useAuthStore } from "@/lib/stores/auth-store"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Building2, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"

export function WorkspaceSwitcher() {
  const { workspace, setWorkspace } = useAuthStore()
  const [newName, setNewName] = useState("")
  const [open, setOpen] = useState(false)

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspaceApi.list(),
  })

  const handleSwitch = async (id: string) => {
    try {
      await workspaceApi.switch(id)
      setWorkspace({ id, name: "", owner_id: "", created_at: "" })
      window.location.reload()
    } catch {
      toast.error("Failed to switch workspace")
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    try {
      await workspaceApi.create({ name: newName })
      setNewName("")
      setOpen(false)
      toast.success("Workspace created")
      window.location.reload()
    } catch {
      toast.error("Failed to create workspace")
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Select value={workspace?.id} onValueChange={handleSwitch}>
        <SelectTrigger className="w-44 h-8 text-xs" aria-label="Switch workspace">
          <Building2 className="h-3 w-3 mr-1" />
          <SelectValue placeholder="Select workspace" />
        </SelectTrigger>
        <SelectContent>
          {workspaces?.map((ws) => (
            <SelectItem key={ws.id} value={ws.id} className="text-xs">
              {ws.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label="Create workspace">
            <Plus className="h-3 w-3" />
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Workspace</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              placeholder="Workspace name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoComplete="off"
            />
            <Button onClick={handleCreate} className="w-full">
              Create
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
