"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { useAuthStore } from "@/lib/stores/auth-store"
import { useTheme } from "next-themes"
import { useSyncExternalStore, useState, useEffect } from "react"
import { toast } from "sonner"
import { Sun, Moon, Monitor, Check, Bell, Mail, Palette } from "lucide-react"

export default function SettingsPage() {
  const { user } = useAuthStore()
  const { theme, setTheme } = useTheme()
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false)
  const [name, setName] = useState(user?.name ?? "")
  const [emailNotifications, setEmailNotifications] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem("projectpilot-email-notifications")
    if (saved !== null) setEmailNotifications(saved === "true")
  }, [])

  const handleSave = () => {
    localStorage.setItem("projectpilot-email-notifications", String(emailNotifications))
    toast.success("Settings saved")
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <PageHeader title="Settings" description="Manage your account and preferences" />

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Palette className="h-4 w-4 text-muted-foreground" />
            Appearance
          </CardTitle>
          <CardDescription>Choose your theme preference</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            {[
              { value: "light", label: "Light", icon: Sun },
              { value: "dark", label: "Dark", icon: Moon },
              { value: "system", label: "System", icon: Monitor },
            ].map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setTheme(value)}
                disabled={!mounted}
                className={`relative flex flex-col items-center gap-2 rounded-lg border p-4 transition-all ${
                  mounted && theme === value
                    ? "border-primary bg-primary/10"
                    : "border-border hover:border-muted-foreground/30"
                }`}
              >
                <Icon className={`h-5 w-5 ${mounted && theme === value ? "text-primary" : "text-muted-foreground"}`} />
                <span className="text-xs font-medium">{label}</span>
                {mounted && theme === value && (
                  <span className="absolute top-1 right-1">
                    <Check className="h-3 w-3 text-primary" />
                  </span>
                )}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Bell className="h-4 w-4 text-muted-foreground" />
            Notifications
          </CardTitle>
          <CardDescription>Manage how you receive updates about your projects</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Mail className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">Email Notifications</p>
                <p className="text-xs text-muted-foreground">Receive emails when projects complete or workspace changes are made</p>
              </div>
            </div>
            <Switch checked={emailNotifications} onCheckedChange={setEmailNotifications} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
          <CardDescription>Your account information</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="settings-name">Name</Label>
            <Input id="settings-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="settings-email">Email</Label>
            <Input id="settings-email" defaultValue={user?.email ?? ""} disabled />
          </div>
          <Button size="sm" onClick={handleSave}>Save Changes</Button>
        </CardContent>
      </Card>
    </div>
  )
}
