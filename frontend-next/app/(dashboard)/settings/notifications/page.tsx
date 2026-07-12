"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState } from "@/components/shared/empty-state"
import { Bell } from "lucide-react"

export default function NotificationsPage() {
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Notifications" />
      <Card>
        <CardContent className="p-6">
          <EmptyState icon={<Bell className="h-12 w-12 opacity-40" />} title="Notification preferences coming soon" />
        </CardContent>
      </Card>
    </div>
  )
}
