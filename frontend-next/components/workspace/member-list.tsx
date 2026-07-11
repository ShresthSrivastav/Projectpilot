"use client"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import { EmptyState } from "@/components/shared/empty-state"
import { Users, X, Shield, Crown, Eye, User as UserIcon } from "lucide-react"
import { useState } from "react"
import { workspaceApi } from "@/lib/api/workspace"
import { useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import type { WorkspaceMember } from "@/lib/utils/types"
import { motion } from "framer-motion"

const roleIcons = {
  OWNER: Crown,
  ADMIN: Shield,
  MEMBER: UserIcon,
  VIEWER: Eye,
}

const roleColors: Record<string, "default" | "secondary" | "outline" | "destructive" | "success" | "warning" | "accent"> = {
  OWNER: "success",
  ADMIN: "accent",
  MEMBER: "secondary",
  VIEWER: "outline",
}

interface MemberListProps {
  members: WorkspaceMember[] | undefined
  isLoading: boolean
  currentUserId?: string
}

export function MemberList({ members, isLoading, currentUserId }: MemberListProps) {
  const [removeMember, setRemoveMember] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const handleRemove = async () => {
    if (!removeMember) return
    try {
      await workspaceApi.removeMember(removeMember)
      toast.success("Member removed")
      queryClient.invalidateQueries({ queryKey: ["workspace-members"] })
    } catch {
      toast.error("Failed to remove member")
    } finally {
      setRemoveMember(null)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    )
  }

  if (!members || members.length === 0) {
    return (
      <EmptyState
        icon={<Users className="h-12 w-12 opacity-40" />}
        title="No members"
        description="Invite members to your workspace to collaborate"
      />
    )
  }

  return (
    <>
      <div className="space-y-1">
        {members.map((member, i) => {
          const RoleIcon = roleIcons[member.role as keyof typeof roleIcons] ?? UserIcon
          const isSelf = member.user_id === currentUserId

          return (
            <motion.div
              key={member.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="flex items-center gap-3 rounded-md p-2.5 hover:bg-muted/50 transition-colors group"
            >
              <Avatar className="h-9 w-9 ring-1 ring-border">
                <AvatarFallback className="text-xs">
                  {member.name?.[0]?.toUpperCase() ?? "?"}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <p className="text-sm font-medium truncate">{member.name}</p>
                  {isSelf && (
                    <span className="text-[10px] text-muted-foreground">(you)</span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate">{member.email}</p>
              </div>
              <Badge
                variant={roleColors[member.role as keyof typeof roleColors] ?? "secondary"}
                className="flex items-center gap-1 text-[10px] capitalize"
              >
                <RoleIcon className="h-3 w-3" />
                {member.role.toLowerCase()}
              </Badge>
              {!isSelf && member.role !== "OWNER" && (
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Remove member"
                  className="h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={() => setRemoveMember(member.id)}
                >
                  <X className="h-3.5 w-3.5 text-muted-foreground hover:text-error" />
                </Button>
              )}
            </motion.div>
          )
        })}
      </div>

      <ConfirmDialog
        open={!!removeMember}
        onOpenChange={() => setRemoveMember(null)}
        title="Remove Member"
        description="Are you sure you want to remove this member from the workspace? They will lose access to all workspace resources."
        confirmLabel="Remove"
        destructive
        onConfirm={handleRemove}
      />
    </>
  )
}
