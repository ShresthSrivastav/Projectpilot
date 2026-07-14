"use client"

import dynamic from "next/dynamic"
import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { dashboardApi } from "@/lib/api/dashboard"
import { pipelineApi } from "@/lib/api/pipeline"
import { analyticsApi } from "@/lib/api/analytics"
import { PageHeader } from "@/components/shared/page-header"
import { SkeletonCard, SkeletonTable, SkeletonChart } from "@/components/shared/loading-skeleton"
import { StatCard } from "@/components/analytics/stat-card"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { motion } from "framer-motion"
import {
  Sparkles, BarChart3, Clock, FileText, Cpu, HardDrive,
  Activity, ArrowRight, Zap, CheckCircle2, Loader2, Play, Users,
} from "lucide-react"
import Link from "next/link"
import { formatRelativeTime, formatNumber } from "@/lib/utils/formatters"

const MetricChart = dynamic(
  () => import("@/components/analytics/metric-chart").then((m) => ({ default: m.MetricChart })),
  { ssr: false, loading: () => <SkeletonChart /> }
)

export default function DashboardPage() {
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ["dashboard-status"],
    queryFn: () => dashboardApi.status(),
  })

  const { data: jobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => pipelineApi.jobs(),
  })

  const { data: timeline } = useQuery({
    queryKey: ["dashboard-timeline"],
    queryFn: () => dashboardApi.timeline(10),
  })

  const { data: projectAnalytics } = useQuery({
    queryKey: ["analytics-projects"],
    queryFn: () => analyticsApi.projects(),
  })

  const activeJobs = useMemo(
    () => jobs?.filter((j) => j.status === "running" || j.status === "queued") ?? [],
    [jobs]
  )

  const chartData = useMemo(
    () => {
      if (!projectAnalytics) return []
      const raw = Array.isArray(projectAnalytics) ? projectAnalytics : []
      return raw
        .slice(0, 10)
        .map((p, i) => ({
          name: (p as Record<string, unknown>)?.name as string ?? `Project ${i + 1}`,
          duration: (p as Record<string, unknown>)?.duration as number ?? 0,
          files: (p as Record<string, unknown>)?.files as number ?? 0,
          tokens: (p as Record<string, unknown>)?.tokens as number ?? 0,
        }))
    },
    [projectAnalytics]
  )

  const timelineEvents = (Array.isArray(timeline) ? timeline : []) as Array<{ description?: string; created_at?: string; type?: string }>

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader
          title="Dashboard"
          description="Overview of your projects and system status"
        >
          <Link href="/generate">
            <Button>
              <Sparkles className="mr-2 h-4 w-4" />
              New Project
            </Button>
          </Link>
        </PageHeader>
      </motion.div>

      {statusLoading ? (
        <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} className="!p-4" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="Total Projects" value={status?.total_projects ?? 0} icon={FileText} color="text-primary" trend={{ value: 12, positive: true }} />
          <StatCard label="Active Jobs" value={status?.active_jobs ?? 0} icon={Loader2} color="text-warning" />
          <StatCard label="Files Generated" value={status?.total_files ?? 0} icon={BarChart3} color="text-success" formatter={formatNumber} />
          <StatCard label="Tokens Used" value={status?.total_tokens ?? 0} icon={Zap} color="text-accent" formatter={(v) => `${formatNumber(v)}`} />
          <StatCard label="Avg Duration" value={status?.avg_duration ? `${Math.round(status.avg_duration)}s` : "0s"} icon={Clock} color="text-info" />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-7">
        <div className="lg:col-span-4 space-y-6">
          {chartData.length > 0 ? (
            <MetricChart title="Project Duration Trend" data={chartData} type="area" dataKey="duration" color="var(--color-primary)" height={220} formatY={(v) => `${v}s`} />
          ) : (
            <Card><CardHeader><CardTitle className="text-sm font-medium">Project Duration Trend</CardTitle></CardHeader><CardContent><SkeletonChart /></CardContent></Card>
          )}

          {chartData.length > 0 && (
            <div className="grid gap-6 sm:grid-cols-2">
              <MetricChart title="Files per Project" data={chartData} type="bar" dataKey="files" color="var(--color-accent)" height={200} />
              <MetricChart title="Token Usage per Project" data={chartData} type="bar" dataKey="tokens" color="var(--color-chart-4)" height={200} formatY={(v) => formatNumber(v)} />
            </div>
          )}
        </div>

        <div className="lg:col-span-3 space-y-6">
          <Card>
            <CardHeader><CardTitle className="text-sm font-medium">Resource Usage</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              {[
                { label: "CPU", value: status?.cpu_usage ?? 0, icon: Cpu },
                { label: "Memory", value: status?.memory_usage ?? 0, icon: HardDrive },
                { label: "GPU", value: status?.gpu_usage ?? 0, icon: Cpu },
              ].map((res) => (
                <div key={res.label} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <res.icon className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-medium">{res.label}</span>
                    </div>
                    <span className="text-muted-foreground">{res.value}%</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <motion.div
                      className="h-full rounded-full"
                      style={{ background: res.value > 80 ? "linear-gradient(90deg, var(--color-warning), var(--color-error))" : "linear-gradient(90deg, var(--color-primary), var(--color-accent))" }}
                      initial={{ width: 0 }}
                      animate={{ width: `${res.value}%` }}
                      transition={{ duration: 1, ease: "easeOut" }}
                    />
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm font-medium flex items-center gap-2"><Play className="h-4 w-4 text-muted-foreground" />Active Jobs</CardTitle></CardHeader>
            <CardContent>
              {jobsLoading ? <SkeletonTable rows={3} /> : activeJobs.length === 0 ? (
                <div className="flex flex-col items-center py-6 text-center">
                  <CheckCircle2 className="h-8 w-8 text-success mb-2" />
                  <p className="text-sm text-muted-foreground">No active jobs</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {activeJobs.map((job, i) => (
                    <motion.div key={job.job_id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.1 }}>
                      <Link href={`/generate/${job.job_id}`} className="flex items-center gap-3 rounded-md p-2.5 hover:bg-muted transition-colors group">
                        <div className="relative">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                          <span className="absolute inset-0 animate-ping rounded-full bg-primary/20" />
                        </div>
                        <span className="text-sm flex-1 truncate font-medium group-hover:text-primary transition-colors">{job.project_name ?? job.job_id}</span>
                        <Badge variant="warning" className="text-[10px]">{job.progress}%</Badge>
                      </Link>
                    </motion.div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm font-medium">Quick Actions</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <Link href="/generate"><Button variant="default" size="sm" className="w-full justify-start"><Sparkles className="mr-2 h-4 w-4" />New Project</Button></Link>
              <Link href="/benchmarks"><Button variant="outline" size="sm" className="w-full justify-start"><BarChart3 className="mr-2 h-4 w-4" />Run Benchmark</Button></Link>
              <Link href="/chat"><Button variant="outline" size="sm" className="w-full justify-start"><Zap className="mr-2 h-4 w-4" />Open Chat</Button></Link>
              <Link href="/workspace"><Button variant="outline" size="sm" className="w-full justify-start"><Users className="mr-2 h-4 w-4" />Manage Workspace</Button></Link>
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2"><Activity className="h-4 w-4 text-muted-foreground" />Recent Activity</CardTitle>
            <Link href="/history"><Button variant="ghost" size="sm">View all <ArrowRight className="ml-1 h-3 w-3" /></Button></Link>
          </div>
        </CardHeader>
        <CardContent>
          {timelineEvents.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-center"><Activity className="h-8 w-8 text-muted-foreground mb-2 opacity-40" /><p className="text-sm text-muted-foreground">No recent activity</p></div>
          ) : (
            <div className="space-y-0">
              {timelineEvents.slice(0, 8).map((event, i) => (
                <motion.div key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.05 }} className="flex items-center gap-3 py-2.5 border-b border-border last:border-0">
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted shrink-0"><Zap className="h-3 w-3 text-muted-foreground" /></div>
                  <div className="flex-1 min-w-0"><p className="text-sm truncate">{event.description ?? "Activity"}</p></div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap shrink-0">{event.created_at ? formatRelativeTime(event.created_at) : ""}</span>
                </motion.div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">Recent Projects</CardTitle>
            <Link href="/history"><Button variant="ghost" size="sm">View all <ArrowRight className="ml-1 h-3 w-3" /></Button></Link>
          </div>
        </CardHeader>
        <CardContent>
          {jobsLoading ? <SkeletonTable rows={5} /> : !jobs || jobs.length === 0 ? (
            <div className="flex flex-col items-center py-8 text-center">
              <FileText className="h-8 w-8 text-muted-foreground mb-2 opacity-40" />
              <p className="text-sm font-medium">No projects yet</p>
              <p className="text-xs text-muted-foreground mb-4">Generate your first project to get started</p>
              <Link href="/generate"><Button size="sm"><Sparkles className="mr-2 h-4 w-4" />Generate Project</Button></Link>
            </div>
          ) : (
            <div className="divide-y divide-border">
              {jobs.slice(0, 5).map((job) => (
                <Link key={job.job_id} href={`/history/${job.job_id}`} className="flex items-center gap-4 py-3 hover:bg-muted/50 -mx-6 px-6 transition-colors group">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-primary transition-colors">{job.project_name ?? job.job_id}</p>
                    <p className="text-xs text-muted-foreground font-mono truncate">{job.job_id}</p>
                  </div>
                  <Badge variant={job.status === "complete" ? "success" : job.status === "failed" ? "destructive" : job.status === "running" ? "warning" : "secondary"} className="text-[10px]">{job.status}</Badge>
                  {job.progress > 0 && (
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                        <motion.div className="h-full rounded-full bg-primary" initial={{ width: 0 }} animate={{ width: `${job.progress}%` }} transition={{ duration: 1 }} />
                      </div>
                      <span className="text-xs text-muted-foreground w-8 text-right tabular-nums">{job.progress}%</span>
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
