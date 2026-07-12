"use client"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import { Activity } from "lucide-react"
import { formatRelativeTime } from "@/lib/utils/formatters"
import { motion } from "framer-motion"
import type { Activity as ActivityType } from "@/lib/utils/types"

interface ActivityTimelineProps {
  activity: ActivityType[] | undefined
  isLoading: boolean
}

export function ActivityTimeline({ activity, isLoading }: ActivityTimelineProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3">
            <Skeleton className="h-8 w-8 rounded-full shrink-0" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (!activity || activity.length === 0) {
    return (
      <EmptyState
        icon={<Activity className="h-12 w-12 opacity-40" />}
        title="No activity yet"
        description="Activity from workspace members will appear here"
      />
    )
  }

  return (
    <div className="relative space-y-0">
      {/* Timeline line */}
      <div className="absolute left-4 top-2 bottom-2 w-px bg-border" />

      <div className="space-y-3">
        {activity.map((item, i) => (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
            className="relative flex items-start gap-3 pl-10"
          >
            {/* Timeline dot */}
            <div className="absolute left-[14px] top-2 h-2 w-2 rounded-full border-2 border-primary bg-background" />

            <Avatar className="h-7 w-7 shrink-0 ring-1 ring-border">
              <AvatarFallback className="text-[10px]">
                {item.user_name?.[0]?.toUpperCase() ?? "?"}
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm">
                <span className="font-medium">{item.user_name}</span>{" "}
                <span className="text-muted-foreground">{item.description}</span>
              </p>
              <p className="text-xs text-muted-foreground/60 mt-0.5">
                {item.created_at ? formatRelativeTime(item.created_at) : ""}
              </p>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
