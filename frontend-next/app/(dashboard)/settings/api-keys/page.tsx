"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState } from "@/components/shared/empty-state"
import { Key } from "lucide-react"

export default function ApiKeysPage() {
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <PageHeader title="API Keys" />
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your API Keys</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={<Key className="h-12 w-12 opacity-40" />} title="No API keys" description="API key management coming soon" />
        </CardContent>
      </Card>
    </div>
  )
}
