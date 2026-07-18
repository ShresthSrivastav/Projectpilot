"use client"

import { useRouter } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SkeletonTable } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import { Clock, RefreshCw, Sparkles, ExternalLink } from "lucide-react"

export default function HistoryPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => pipelineApi.jobs(),
    refetchInterval: 10000,
  })

  return (
    <div className="space-y-4">
      <PageHeader
        title="History"
        description="All your generated projects"
      >
        <Button variant="outline" size="sm" onClick={() => queryClient.invalidateQueries({ queryKey: ["jobs"] })}>
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Refresh
        </Button>
        <Button size="sm" onClick={() => router.push("/generate")}>
          <Sparkles className="mr-1.5 h-3.5 w-3.5" /> New Project
        </Button>
      </PageHeader>

      {isLoading ? (
        <Card><CardContent className="p-6"><SkeletonTable rows={8} /></CardContent></Card>
      ) : !jobs || jobs.length === 0 ? (
        <EmptyState
          icon={<Clock className="h-12 w-12 opacity-40" />}
          title="No projects yet"
          description="Generate your first project to see it here"
          action={{ label: "Generate Project", onClick: () => router.push("/generate") }}
        />
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {jobs.map((job) => {
                const handleClick = () => router.push(`/history/${job.job_id}`)
                return (
                  <div
                    key={job.job_id}
                    className="flex items-center gap-4 px-6 py-4 hover:bg-muted/50 cursor-pointer transition-colors group"
                    role="button"
                    tabIndex={0}
                    onClick={handleClick}
                    onKeyDown={(e) => e.key === 'Enter' && handleClick()}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{job.project_name ?? job.job_id}</p>
                      <p className="text-xs text-muted-foreground font-mono">{job.job_id}</p>
                    </div>
                    <Badge
                      variant={job.status === "complete" ? "success" : job.status === "failed" ? "destructive" : job.status === "running" ? "warning" : "secondary"}
                      className="text-[10px]"
                    >
                      {job.status}
                    </Badge>
                    {job.tests_total ? (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {job.tests_passed}/{job.tests_total} tests
                      </span>
                    ) : null}
                    <ExternalLink className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
