"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useQuery } from "@tanstack/react-query"
import { workspaceApi } from "@/lib/api/workspace"
import { useAuthStore } from "@/lib/stores/auth-store"
import { InviteDialog } from "@/components/workspace/invite-dialog"
import { MemberList } from "@/components/workspace/member-list"
import { ActivityTimeline } from "@/components/workspace/activity-timeline"
import { Users, Activity, Settings } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"

export default function WorkspacePage() {
  const { user, workspace } = useAuthStore()

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ["workspace-members"],
    queryFn: () => workspaceApi.members(),
  })

  const { data: activity, isLoading: activityLoading } = useQuery({
    queryKey: ["workspace-activity"],
    queryFn: () => workspaceApi.activity(),
  })

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader
          title={workspace?.name ?? "Workspace"}
          description="Manage your workspace and team"
        >
          <Link href="/workspace/settings">
            <Button variant="outline" size="sm">
              <Settings className="mr-1.5 h-4 w-4" /> Settings
            </Button>
          </Link>
        </PageHeader>
      </motion.div>

      <Tabs defaultValue="members" className="space-y-4">
        <TabsList>
          <TabsTrigger value="members">
            <Users className="mr-1.5 h-3.5 w-3.5" />
            Members
          </TabsTrigger>
          <TabsTrigger value="activity">
            <Activity className="mr-1.5 h-3.5 w-3.5" />
            Activity
          </TabsTrigger>
        </TabsList>

        <TabsContent value="members" className="space-y-0">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  Team Members
                  {members && (
                    <span className="text-xs font-normal text-muted-foreground">
                      ({members.length})
                    </span>
                  )}
                </CardTitle>
                <InviteDialog />
              </div>
            </CardHeader>
            <CardContent>
              <MemberList
                members={members}
                isLoading={membersLoading}
                currentUserId={user?.id}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activity">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                Activity Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ActivityTimeline
                activity={activity}
                isLoading={activityLoading}
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
