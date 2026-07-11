"use client"

import { useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { SkeletonTable } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import { Clock } from "lucide-react"


export default function HistoryPage() {
  const router = useRouter()
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => pipelineApi.jobs(),
  })

  if (isLoading) {
    return (
      <div className="space-y-4">
        <PageHeader title="History" />
        <Card><CardContent className="p-6"><SkeletonTable rows={8} /></CardContent></Card>
      </div>
    )
  }

  if (!jobs || jobs.length === 0) {
    return (
      <div className="space-y-4">
        <PageHeader title="History" />
        <EmptyState
          icon={<Clock className="h-12 w-12 opacity-40" />}
          title="No projects yet"
          description="Generate your first project to see it here"
          action={{ label: "Generate Project", onClick: () => router.push("/generate") }}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <PageHeader title="History" description="All your generated projects" />
      <Card>
        <CardContent className="p-0">
          <div className="divide-y divide-border">
            {jobs.map((job) => {
              const handleClick = () => router.push(`/history/${job.job_id}`)
              return (
                <div
                  key={job.job_id}
                  className="flex items-center gap-4 px-6 py-4 hover:bg-muted/50 cursor-pointer transition-colors"
                  role="button"
                  tabIndex={0}
                  onClick={handleClick}
                  onKeyDown={(e) => e.key === 'Enter' && handleClick()}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{job.project_name ?? job.job_id}</p>
                    <p className="text-xs text-muted-foreground">{job.job_id}</p>
                  </div>
                  <Badge
                    variant={job.status === "complete" ? "success" : job.status === "failed" ? "destructive" : job.status === "running" ? "warning" : "secondary"}
                    className="text-[10px]"
                  >
                    {job.status}
                  </Badge>
                  {job.tests_total ? (
                    <span className="text-xs text-muted-foreground w-16 text-right">
                      {job.tests_passed}/{job.tests_total} tests
                    </span>
                  ) : null}
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
