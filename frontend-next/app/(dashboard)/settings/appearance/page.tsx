"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { useTheme } from "next-themes"
import { useSyncExternalStore } from "react"
import { Sun, Moon, Monitor, Check } from "lucide-react"

export default function AppearancePage() {
  const { theme, setTheme } = useTheme()
  const mounted = useSyncExternalStore(() => () => {}, () => true, () => false)

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="Appearance" />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Theme</CardTitle>
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
    </div>
  )
}
