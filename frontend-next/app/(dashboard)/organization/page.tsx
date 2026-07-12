"use client"

import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState } from "@/components/shared/empty-state"
import { Building2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export default function OrganizationPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Organization" description="Multi-repository intelligence">
        <Button variant="outline" size="sm">Create Organization</Button>
      </PageHeader>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Organizations</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState icon={<Building2 className="h-12 w-12 opacity-40" />} title="No organizations" description="Create an organization to manage multiple repositories" />
        </CardContent>
      </Card>
    </div>
  )
}
