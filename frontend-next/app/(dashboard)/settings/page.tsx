"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"
import { useAuthStore } from "@/lib/stores/auth-store"
import { useTheme } from "next-themes"
import { useSyncExternalStore, useState } from "react"
import { toast } from "sonner"
import { Sun, Moon, Monitor, Check } from "lucide-react"

export default function SettingsPage() {
  const { user } = useAuthStore()
  const { theme, setTheme } = useTheme()
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false)
  const [name, setName] = useState(user?.name ?? "")

  const handleSave = () => {
    toast.success("Settings saved")
  }

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Settings" description="Manage your account and preferences" />

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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appearance</CardTitle>
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
                className={`flex flex-col items-center gap-2 rounded-lg border p-4 transition-all ${
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
    </div>
  )
}
