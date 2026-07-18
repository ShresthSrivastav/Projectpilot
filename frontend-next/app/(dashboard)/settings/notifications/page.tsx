"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { useState } from "react"
import { toast } from "sonner"
import { Bell, Mail, MessageSquare, Sparkles, Users, GitBranch } from "lucide-react"

interface ToggleRowProps {
  icon: React.ReactNode
  label: string
  description: string
  checked: boolean
  onChange: (v: boolean) => void
}

function ToggleRow({ icon, label, description, checked, onChange }: ToggleRowProps) {
  return (
    <div className="flex items-center justify-between py-3">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 text-muted-foreground">{icon}</div>
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-muted'}`}
      >
        <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${checked ? 'translate-x-[18px]' : 'translate-x-1'}`} />
      </button>
    </div>
  )
}

export default function NotificationsPage() {
  const [settings, setSettings] = useState({
    emailGeneration: true,
    emailChanges: true,
    inAppGeneration: true,
    inAppChanges: true,
    inAppMentions: true,
    emailWeeklyDigest: false,
  })

  const toggle = (key: keyof typeof settings) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }))
    toast.success("Notification preference updated")
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Notifications" description="Manage how you receive notifications" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Mail className="h-4 w-4 text-muted-foreground" />
            Email Notifications
          </CardTitle>
          <CardDescription>Receive email updates for important events</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <ToggleRow
            icon={<Sparkles className="h-4 w-4" />}
            label="Project generation started"
            description="Get an email when your project generation starts"
            checked={settings.emailGeneration}
            onChange={() => toggle("emailGeneration")}
          />
          <ToggleRow
            icon={<GitBranch className="h-4 w-4" />}
            label="Workspace changes"
            description="Get an email when team members make changes to shared projects"
            checked={settings.emailChanges}
            onChange={() => toggle("emailChanges")}
          />
          <ToggleRow
            icon={<Bell className="h-4 w-4" />}
            label="Weekly digest"
            description="Receive a weekly summary of all project activity"
            checked={settings.emailWeeklyDigest}
            onChange={() => toggle("emailWeeklyDigest")}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Bell className="h-4 w-4 text-muted-foreground" />
            In-App Notifications
          </CardTitle>
          <CardDescription>Notifications shown within the application</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <ToggleRow
            icon={<Sparkles className="h-4 w-4" />}
            label="Project updates"
            description="Get notified when your projects finish generating"
            checked={settings.inAppGeneration}
            onChange={() => toggle("inAppGeneration")}
          />
          <ToggleRow
            icon={<Users className="h-4 w-4" />}
            label="Workspace activity"
            description="See when team members make changes to shared projects"
            checked={settings.inAppChanges}
            onChange={() => toggle("inAppChanges")}
          />
          <ToggleRow
            icon={<MessageSquare className="h-4 w-4" />}
            label="Mentions"
            description="Get notified when someone mentions you in a comment"
            checked={settings.inAppMentions}
            onChange={() => toggle("inAppMentions")}
          />
        </CardContent>
      </Card>
    </div>
  )
}
