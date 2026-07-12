"use client"

import { useQuery } from "@tanstack/react-query"
import { evaluationApi } from "@/lib/api/evaluation"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SkeletonCard, SkeletonChart } from "@/components/shared/loading-skeleton"
import { EmptyState } from "@/components/shared/empty-state"
import dynamic from "next/dynamic"

const MetricChart = dynamic(
  () => import("@/components/analytics/metric-chart").then((m) => ({ default: m.MetricChart })),
  { ssr: false, loading: () => <SkeletonChart /> }
)
import {
  ClipboardCheck, TrendingUp, Trophy, Play,
  Loader2,
} from "lucide-react"
import { toast } from "sonner"
import { formatRelativeTime } from "@/lib/utils/formatters"
import { motion } from "framer-motion"
import { useState } from "react"

function EvaluationRow({
  run,
}: {
  run: Record<string, unknown>
  rank?: number
}) {
  return (
    <motion.div className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Badge
            variant={(run.status as string) === "complete" ? "success" : (run.status as string) === "failed" ? "destructive" : "warning"}
            className="text-[10px]"
          >
            {run.status as string}
          </Badge>
          <span className="text-xs text-muted-foreground font-mono">
            {(run.id as string)?.substring(0, 8)}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          {run.created_at ? formatRelativeTime(run.created_at as string) : ""}
        </p>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <p className="text-sm font-semibold tabular-nums">{(run.autonomy_score as number)?.toFixed(1) ?? "-"}</p>
          <p className="text-[10px] text-muted-foreground">Autonomy</p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold tabular-nums">{(run.success_rate as number)?.toFixed(0) ?? "-"}%</p>
          <p className="text-[10px] text-muted-foreground">Success</p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold tabular-nums">
            {run.cost != null ? `$${(run.cost as number).toFixed(2)}` : "-"}
          </p>
          <p className="text-[10px] text-muted-foreground">Cost</p>
        </div>
      </div>
    </motion.div>
  )
}

export default function EvaluationPage() {
  const [running, setRunning] = useState(false)

  const { data: history, isLoading: hLoading } = useQuery({
    queryKey: ["evaluation-history"],
    queryFn: () => evaluationApi.history({ limit: 20 }),
  })

  const { data: leaderboards } = useQuery({
    queryKey: ["evaluation-leaderboards"],
    queryFn: () => evaluationApi.leaderboards({ limit: 20 }),
  })

  useQuery({
    queryKey: ["evaluation-comparison"],
    queryFn: () => evaluationApi.comparison({ limit: 20 }),
  })

  const handleRun = async () => {
    setRunning(true)
    try {
      await evaluationApi.run()
      toast.success("Evaluation started")
    } catch {
      toast.error("Failed to start evaluation")
    } finally {
      setRunning(false)
    }
  }

  const historyData = Array.isArray(history) ? history : []
  const leaderboardData = Array.isArray(leaderboards) ? leaderboards : []

  // Build trend chart data
  const trendData = historyData
    .slice(0, 15)
    .reverse()
    .map((h: Record<string, unknown>, i) => ({
      name: h.created_at
        ? new Date(h.created_at as string).toLocaleDateString()
        : `#${i + 1}`,
      autonomy: (h.autonomy_score as number) ?? 0,
      success: (h.success_rate as number) ?? 0,
    }))

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Evaluation" description="Continuous evaluation and quality metrics">
          <Button onClick={handleRun} disabled={running}>
            {running ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-1.5 h-4 w-4" />
            )}
            Run Evaluation
          </Button>
        </PageHeader>
      </motion.div>

      <Tabs defaultValue="history" className="space-y-4">
        <TabsList>
          <TabsTrigger value="history">
            <ClipboardCheck className="mr-1.5 h-3.5 w-3.5" /> History
          </TabsTrigger>
          <TabsTrigger value="trends">
            <TrendingUp className="mr-1.5 h-3.5 w-3.5" /> Trends
          </TabsTrigger>
          <TabsTrigger value="leaderboards">
            <Trophy className="mr-1.5 h-3.5 w-3.5" /> Leaderboards
          </TabsTrigger>
        </TabsList>

        <TabsContent value="history" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Evaluation History</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {hLoading ? (
                <SkeletonCard count={5} />
              ) : historyData.length === 0 ? (
                <EmptyState
                  icon={<ClipboardCheck className="h-12 w-12 opacity-40" />}
                  title="No evaluations yet"
                  description="Run your first evaluation to track quality metrics"
                />
              ) : (
                historyData.map((run, i) => (
                  <EvaluationRow key={(run.id as string) ?? i} run={run} />
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trends">
          <div className="space-y-6">
            {trendData.length > 0 ? (
              <>
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                >
                  <MetricChart
                    title="Autonomy Score Trend"
                    data={trendData}
                    type="line"
                    dataKey="autonomy"
                    color="var(--color-primary)"
                    height={280}
                  />
                </motion.div>
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                >
                  <MetricChart
                    title="Success Rate Trend"
                    data={trendData}
                    type="area"
                    dataKey="success"
                    color="var(--color-success)"
                    height={280}
                    formatY={(v) => `${v}%`}
                  />
                </motion.div>
              </>
            ) : (
              <Card>
                <CardContent>
                  <EmptyState
                    icon={<TrendingUp className="h-12 w-12 opacity-40" />}
                    title="No trend data"
                    description="Run multiple evaluations to see trends over time"
                  />
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="leaderboards">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Evaluation Leaderboards</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {leaderboardData.length === 0 ? (
                <EmptyState
                  icon={<Trophy className="h-12 w-12 opacity-40" />}
                  title="No leaderboard data"
                  description="Run evaluations to populate the leaderboard"
                />
              ) : (
                leaderboardData.slice(0, 10).map((entry, i) => {
                  const e = entry as Record<string, unknown>
                  return (
                    <motion.div
                      key={(e.id as string) ?? i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="flex items-center gap-3 rounded-md border border-border p-3"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">
                        #{i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">
                          {(e.category as string) ?? (e.id as string)?.substring(0, 8)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Score: {(e.score as number)?.toFixed(1) ?? "-"}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-lg font-semibold tabular-nums text-primary">
                          {(e.score as number)?.toFixed(1) ?? "-"}
                        </p>
                      </div>
                    </motion.div>
                  )
                })
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
