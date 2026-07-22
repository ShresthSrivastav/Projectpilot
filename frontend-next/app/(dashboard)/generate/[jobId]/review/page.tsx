"use client"

import { useParams, useRouter } from "next/navigation"
import { useState, useEffect, useCallback } from "react"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SkeletonCard, SkeletonChart } from "@/components/shared/loading-skeleton"
import { FileTree } from "@/components/shared/file-tree"
import { CodeViewer } from "@/components/shared/code-viewer"
import { useJobStatus, useJobFiles } from "@/lib/hooks/use-job-polling"
import { pipelineApi } from "@/lib/api/pipeline"
import { useQuery } from "@tanstack/react-query"
import {
  CheckCircle2, XCircle, AlertTriangle, Info,
  FileCode, ScrollText, Sparkles, Download,
  ArrowLeft, RotateCw,
} from "lucide-react"
import { motion } from "framer-motion"
import { toast } from "sonner"
import type { ReviewResponse } from "@/lib/utils/types"

export default function ReviewPage() {
  const params = useParams()
  const router = useRouter()
  const jobId = params.jobId as string
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [selectedContent, setSelectedContent] = useState<string | undefined>(undefined)

  const { data: job, isLoading } = useJobStatus(jobId)
  const { data: files, loadFileContent, hasLoaded } = useJobFiles(job?.job_id ?? null)

  useEffect(() => {
    if (files && selectedFile && !hasLoaded(selectedFile)) {
      loadFileContent(selectedFile)
    }
  }, [selectedFile, files, hasLoaded, loadFileContent])

  const reviewFromJob = (() => {
    if (!job?.review_summary) return null
    try {
      const parsed = JSON.parse(job.review_summary as string)
      return parsed as ReviewResponse
    } catch {
      return null
    }
  })()

  const { data: review, isLoading: reviewLoading, isFetching: reviewFetching, refetch: refetchReview } = useQuery({
    queryKey: ["job", jobId, "review"],
    queryFn: () => pipelineApi.review(jobId, { model: "cloud" }),
    enabled: (job?.status === "complete" || job?.status === "partial") && !reviewFromJob,
  })

  const effectiveReview = review || reviewFromJob

  const handleFileSelect = useCallback((path: string, content?: string) => {
    setSelectedFile(path)
    if (content) setSelectedContent(content)
  }, [])

  const handleDownload = async () => {
    try {
      const blob = await pipelineApi.download(jobId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${job?.project_name ?? "project"}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast.success("Download started")
    } catch {
      toast.error("Failed to download project")
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Review" />
        <SkeletonCard count={3} />
      </div>
    )
  }

  const errorCount = effectiveReview?.issues?.filter((i) => i.severity === "error").length ?? 0
  const warningCount = effectiveReview?.issues?.filter((i) => i.severity === "warning").length ?? 0
  const infoCount = effectiveReview?.issues?.filter((i) => i.severity === "info").length ?? 0

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title={`Review: ${job?.project_name ?? "Project"}`}>
          <Button variant="outline" size="sm" onClick={() => router.push(`/generate/${jobId}`)}>
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
            Back to Status
          </Button>
          <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="mr-1.5 h-3.5 w-3.5" />
            Download
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetchReview()} disabled={reviewFetching}>
            {reviewFetching ? (
              <RotateCw className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
            )}
            {reviewFetching ? "Reviewing..." : "Re-review"}
          </Button>
        </PageHeader>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        <Card>
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <XCircle className="h-4 w-4 text-error" />
              <span className="text-2xl font-semibold tabular-nums text-error">{errorCount}</span>
            </div>
            <p className="text-xs text-muted-foreground">Errors</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <AlertTriangle className="h-4 w-4 text-warning" />
              <span className="text-2xl font-semibold tabular-nums text-warning">{warningCount}</span>
            </div>
            <p className="text-xs text-muted-foreground">Warnings</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Info className="h-4 w-4 text-primary" />
              <span className="text-2xl font-semibold tabular-nums text-primary">{infoCount}</span>
            </div>
            <p className="text-xs text-muted-foreground">Suggestions</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Sparkles className="h-4 w-4 text-accent" />
              <span className="text-2xl font-semibold tabular-nums text-accent">
                {effectiveReview?.score ?? "--"}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">AI Score</p>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <FileCode className="h-4 w-4 text-muted-foreground" />
                Files
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              <FileTree
                files={files}
                selectedPath={selectedFile}
                onSelect={handleFileSelect}
              />
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-3 space-y-6">
          {selectedFile && selectedContent !== undefined ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <Card>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                      <FileCode className="h-4 w-4 text-muted-foreground" />
                      {selectedFile}
                    </CardTitle>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-xs"
                      onClick={() => { setSelectedFile(null); setSelectedContent(undefined) }}
                    >
                      Close
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <CodeViewer content={selectedContent} fileName={selectedFile} height={500} />
                </CardContent>
              </Card>
            </motion.div>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ScrollText className="h-4 w-4 text-muted-foreground" />
                AI Review
              </CardTitle>
            </CardHeader>
            <CardContent>
              {reviewLoading || reviewFetching ? (
                <SkeletonChart />
              ) : effectiveReview?.error ? (
                <div className="rounded-md border border-warning/30 bg-warning/5 p-4 text-sm text-muted-foreground">
                  {String(effectiveReview.error)}
                </div>
              ) : !effectiveReview ? (
                <div className="flex flex-col items-center py-8">
                  <Sparkles className="h-10 w-10 text-muted-foreground mb-3 animate-pulse" />
                  <p className="text-sm font-medium">Review not available yet</p>
                  <p className="text-xs text-muted-foreground mt-1 mb-4">Run a review to get AI feedback on your project</p>
                  <Button size="sm" onClick={() => refetchReview()} disabled={reviewFetching}>
                    <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                    Run Review
                  </Button>
                </div>
              ) : effectiveReview.issues.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center py-8"
                >
                  <CheckCircle2 className="h-10 w-10 text-success mb-3" />
                  <p className="text-sm font-medium">No issues found</p>
                  <p className="text-xs text-muted-foreground mt-1">Your project looks clean</p>
                </motion.div>
              ) : (
                <div className="space-y-2">
                  {effectiveReview.issues.map((issue, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="flex items-start gap-3 rounded-md border border-border p-3"
                    >
                      {issue.severity === "error" ? (
                        <XCircle className="h-4 w-4 text-error mt-0.5 shrink-0" />
                      ) : issue.severity === "warning" ? (
                        <AlertTriangle className="h-4 w-4 text-warning mt-0.5 shrink-0" />
                      ) : (
                        <Info className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              issue.severity === "error" ? "destructive" :
                              issue.severity === "warning" ? "warning" : "secondary"
                            }
                            className="text-[10px]"
                          >
                            {issue.severity}
                          </Badge>
                          {issue.file && (
                            <button
                              onClick={() => handleFileSelect(issue.file!, undefined)}
                              className="text-[10px] font-mono text-muted-foreground/70 hover:text-primary cursor-pointer"
                            >
                              {issue.file}{issue.line ? `:${issue.line}` : ""}
                            </button>
                          )}
                        </div>
                        <p className="text-sm mt-1">{issue.message}</p>
                      </div>
                    </motion.div>
                  ))}

                  {effectiveReview.summary && (
                    <div className="mt-4 rounded-md bg-muted/30 p-3">
                      <p className="text-xs text-muted-foreground">{effectiveReview.summary}</p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
