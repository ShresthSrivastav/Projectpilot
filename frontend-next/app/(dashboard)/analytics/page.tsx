"use client"

import { useQuery } from "@tanstack/react-query"
import { analyticsApi } from "@/lib/api/analytics"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { SkeletonCard, SkeletonChart } from "@/components/shared/loading-skeleton"
import { StatCard } from "@/components/analytics/stat-card"
import dynamic from "next/dynamic"

const MetricChart = dynamic(
  () => import("@/components/analytics/metric-chart").then((m) => ({ default: m.MetricChart })),
  { ssr: false, loading: () => <SkeletonChart /> }
)
import { BarChart3, FileText, Zap, Clock, CheckCircle2 } from "lucide-react"
import { formatNumber } from "@/lib/utils/formatters"
import { motion } from "framer-motion"
import { useMemo } from "react"

export default function AnalyticsPage() {
  const { data: overview, isLoading } = useQuery({
    queryKey: ["analytics-overview"],
    queryFn: () => analyticsApi.overview(),
  })

  const { data: projects } = useQuery({
    queryKey: ["analytics-projects"],
    queryFn: () => analyticsApi.projects(),
  })

  const chartData = useMemo(() => {
    if (!Array.isArray(projects)) return []
    return (projects as Array<Record<string, unknown>>)
      .slice(0, 15)
      .map((p, i) => ({
        name: (p.project_name as string) ?? `Project ${i + 1}`,
        duration: Number(p.total_duration_ms ?? p.duration ?? 0) / (p.total_duration_ms ? 1000 : 1),
        files: Number(p.file_count ?? p.files ?? 0),
        tokens: Number(p.token_usage ?? p.tokens ?? 0),
        success_rate: ["success", "complete"].includes(String(p.status)) ? 100 : 0,
      }))
  }, [projects])

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Analytics" description="Project metrics and insights" />
      </motion.div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonCard key={i} className="!p-4" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <StatCard
            label="Total Projects"
            value={(overview?.total_projects as number) ?? 0}
            icon={BarChart3}
            color="text-primary"
          />
          <StatCard
            label="Total Files"
            value={(overview?.total_files as number) ?? 0}
            icon={FileText}
            color="text-success"
            formatter={formatNumber}
          />
          <StatCard
            label="Tokens Used"
            value={(overview?.total_tokens as number) ?? 0}
            icon={Zap}
            color="text-accent"
            formatter={(v) => formatNumber(v)}
          />
          <StatCard
            label="Success Rate"
            value={(overview?.success_rate as number) ?? 0}
            icon={CheckCircle2}
            color="text-success"
            formatter={(v) => `${v}%`}
          />
          <StatCard
            label="Avg Duration"
            value={(overview?.avg_duration as number) ?? 0}
            icon={Clock}
            color="text-info"
            formatter={(v) => `${Math.round(v)}s`}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Duration trend */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <MetricChart
            title="Project Duration"
            data={chartData}
            type="area"
            dataKey="duration"
            color="var(--color-primary)"
            height={280}
            formatY={(v) => `${v}s`}
          />
        </motion.div>

        {/* Files per project */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <MetricChart
            title="Files per Project"
            data={chartData}
            type="bar"
            dataKey="files"
            color="var(--color-accent)"
            height={280}
          />
        </motion.div>

        {/* Token usage */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <MetricChart
            title="Token Usage per Project"
            data={chartData}
            type="bar"
            dataKey="tokens"
            color="var(--color-chart-4)"
            height={280}
            formatY={(v) => formatNumber(v)}
          />
        </motion.div>

        {/* Success rate */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <MetricChart
            title="Success Rate per Project"
            data={chartData}
            type="line"
            dataKey="success_rate"
            color="var(--color-success)"
            height={280}
            formatY={(v) => `${v}%`}
          />
        </motion.div>
      </div>

      {/* Summary Table */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              Project Summary
            </CardTitle>
          </CardHeader>
          <CardContent>
            {chartData.length === 0 ? (
              <div className="flex flex-col items-center py-8 text-center">
                <BarChart3 className="h-8 w-8 text-muted-foreground mb-2 opacity-40" />
                <p className="text-sm text-muted-foreground">No project data available</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-3 text-xs font-medium text-muted-foreground">Project</th>
                      <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Duration</th>
                      <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Files</th>
                      <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Tokens</th>
                      <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Success</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.map((row, i) => (
                      <tr
                        key={i}
                        className="border-b border-border last:border-0 hover:bg-muted/50 transition-colors"
                      >
                        <td className="py-2 px-3 font-mono text-xs">{row.name}</td>
                        <td className="py-2 px-3 text-right font-mono text-xs text-muted-foreground">{row.duration}s</td>
                        <td className="py-2 px-3 text-right font-mono text-xs text-muted-foreground">{row.files}</td>
                        <td className="py-2 px-3 text-right font-mono text-xs text-muted-foreground">{formatNumber(row.tokens as number)}</td>
                        <td className="py-2 px-3 text-right">
                          <span className={`text-xs font-mono ${(row.success_rate as number) >= 80 ? "text-success" : (row.success_rate as number) >= 50 ? "text-warning" : "text-error"}`}>
                            {row.success_rate}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </div>
  )
}
