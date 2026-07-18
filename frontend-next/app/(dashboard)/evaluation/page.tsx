"use client"

import { useQuery } from "@tanstack/react-query"
import { useQueryClient } from "@tanstack/react-query"
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
  Loader2, BarChart3, Target,
} from "lucide-react"
import { toast } from "sonner"
import { formatRelativeTime } from "@/lib/utils/formatters"
import { motion } from "framer-motion"
import { useState, useMemo } from "react"

export default function EvaluationPage() {
  const [running, setRunning] = useState(false)
  const queryClient = useQueryClient()

  const { data: history, isLoading: hLoading } = useQuery({
    queryKey: ["evaluation-history"],
    queryFn: () => evaluationApi.history({ limit: 50 }),
    refetchInterval: 10000,
  })

  const { data: leaderboards } = useQuery({
    queryKey: ["evaluation-leaderboards"],
    queryFn: () => evaluationApi.leaderboards({ limit: 20 }),
  })

  const { data: reports } = useQuery({
    queryKey: ["evaluation-reports"],
    queryFn: () => evaluationApi.reports({ limit: 5 }),
  })

  const { data: regressions } = useQuery({
    queryKey: ["evaluation-regressions"],
    queryFn: () => evaluationApi.regressions({ dismissed: false, limit: 10 }),
  })

  const handleRun = async () => {
    setRunning(true)
    try {
      await evaluationApi.run()
      await queryClient.invalidateQueries({ queryKey: ["evaluation-history"] })
      await queryClient.invalidateQueries({ queryKey: ["evaluation-reports"] })
      toast.success("Evaluation started")
    } catch {
      toast.error("Failed to start evaluation")
    } finally {
      setRunning(false)
    }
  }

  const historyData = Array.isArray(history) ? history : []
  const leaderboardData = Array.isArray(leaderboards) ? leaderboards : []
  const reportList = Array.isArray(reports) ? reports : []
  const regressionList = Array.isArray(regressions) ? regressions : []

  const avgAutonomy = historyData.length > 0
    ? historyData.reduce((s, h) => s + Number((h as Record<string, unknown>).autonomy_score ?? 0), 0) / historyData.length
    : 0
  const avgSuccess = historyData.length > 0
    ? historyData.reduce((s, h) => s + Number((h as Record<string, unknown>).success_rate ?? 0), 0) / historyData.length
    : 0
  const avgCost = historyData.length > 0
    ? historyData.reduce((s, h) => s + Number((h as Record<string, unknown>).cost ?? (h as Record<string, unknown>).total_cost ?? 0), 0) / historyData.length
    : 0

  const trendData = historyData
    .slice(0, 20)
    .reverse()
    .map((h: Record<string, unknown>, i) => ({
      name: h.created_at
        ? new Date(h.created_at as string).toLocaleDateString()
        : `#${i + 1}`,
      autonomy: Number(h.autonomy_score ?? 0),
      success: Number(h.success_rate ?? 0),
      cost: Number(h.cost ?? h.total_cost ?? 0),
    }))

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title="Evaluation" description="Quality metrics and analytics">
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

      {historyData.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-2xl font-semibold tabular-nums text-primary">{avgAutonomy.toFixed(1)}</p>
              <div className="flex items-center justify-center gap-1 mt-1">
                <Target className="h-3 w-3 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Avg Autonomy Score</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-2xl font-semibold tabular-nums text-success">{(avgSuccess * 100).toFixed(0)}%</p>
              <div className="flex items-center justify-center gap-1 mt-1">
                <BarChart3 className="h-3 w-3 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Avg Success Rate</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-2xl font-semibold tabular-nums text-warning">${avgCost.toFixed(2)}</p>
              <div className="flex items-center justify-center gap-1 mt-1">
                <TrendingUp className="h-3 w-3 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Avg Cost per Run</p>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4 text-center">
              <p className="text-2xl font-semibold tabular-nums text-accent">{regressionList.length}</p>
              <div className="flex items-center justify-center gap-1 mt-1">
                <ClipboardCheck className="h-3 w-3 text-muted-foreground" />
                <p className="text-xs text-muted-foreground">Open Regressions</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

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
                historyData.map((run, i) => {
                  const r = run as Record<string, unknown>
                  return (
                    <motion.div
                      key={(r.id as string) ?? i}
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.02 }}
                      className="flex items-center gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge
                            variant={(r.status as string) === "complete" ? "success" : (r.status as string) === "failed" ? "destructive" : "warning"}
                            className="text-[10px]"
                          >
                            {r.status as string}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {r.created_at ? formatRelativeTime(r.created_at as string) : ""}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="tabular-nums">
                          <span className="text-muted-foreground text-[10px]">Autonomy: </span>
                          <span className="font-medium">{(r.autonomy_score as number)?.toFixed(1) ?? "-"}</span>
                        </span>
                        <span className="tabular-nums">
                          <span className="text-muted-foreground text-[10px]">Success: </span>
                          <span className="font-medium">{(r.success_rate as number)?.toFixed(0) ?? "-"}%</span>
                        </span>
                      </div>
                    </motion.div>
                  )
                })
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
                    formatY={(v) => `${(v * 100).toFixed(0)}%`}
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

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Latest Report</CardTitle></CardHeader>
          <CardContent>
            {reportList.length > 0 ? (
              <div className="space-y-2">
                <p className="text-sm font-medium">{String((reportList[0] as Record<string, unknown>).title ?? "Evaluation report")}</p>
                <p className="text-xs text-muted-foreground">{String((reportList[0] as Record<string, unknown>).summary ?? "No summary available")}</p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Run an evaluation to create a report.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Open Regressions</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{regressionList.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Issues needing attention</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Total Runs</CardTitle></CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{historyData.length}</p>
            <p className="text-xs text-muted-foreground mt-1">Evaluation runs completed</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
