"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useTheme } from "next-themes"
import { Switch } from "@/components/ui/switch"

export default function AppearancePage() {
  const { theme, setTheme } = useTheme()
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Appearance" />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Theme</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <p className="text-sm">Dark Mode</p>
            <Switch checked={theme === "dark"} onCheckedChange={(c) => setTheme(c ? "dark" : "light")} aria-label="Toggle dark mode" />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
