"use client"

import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { AgentPipeline } from "@/components/generate/agent-pipeline"
import { FileTree } from "@/components/shared/file-tree"
import { CodeViewer } from "@/components/shared/code-viewer"
import { useJobStatus, useJobFiles } from "@/lib/hooks/use-job-polling"
import {
  Loader2,
  XCircle,
  FileText,
  Download,
  StopCircle,
  ChevronRight,
  BarChart3,
  Bug,
  FileCode,
} from "lucide-react"
import { motion } from "framer-motion"
import { toast } from "sonner"

export default function JobDetailPage() {
  const params = useParams()
  const router = useRouter()
  const jobId = params.jobId as string
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [selectedContent, setSelectedContent] = useState<string | undefined>(undefined)

  const { data: job, isLoading } = useJobStatus(jobId)
  const { data: files } = useJobFiles(job?.job_id ?? null)

  const handleCancel = async () => {
    try {
      await pipelineApi.cancel(jobId)
      toast.success("Job cancelled")
    } catch {
      toast.error("Failed to cancel job")
    }
  }

  const handleFileSelect = (path: string, content?: string) => {
    setSelectedFile(path)
    setSelectedContent(content)
  }

  const handleDownload = async () => {
    try {
      const blob = await pipelineApi.download(jobId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${job?.project_name ?? jobId}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error("Download failed")
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto space-y-6">
        <PageHeader title="Loading..." />
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3 space-y-6">
            <SkeletonCard count={2} />
          </div>
          <div className="lg:col-span-2">
            <SkeletonCard />
          </div>
        </div>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <XCircle className="h-8 w-8 text-error mb-2" />
        <p className="text-sm text-muted-foreground">Job not found</p>
      </div>
    )
  }

  const isRunning = job.status === "running" || job.status === "queued"
  const isComplete = job.status === "complete"
  const isFailed = job.status === "failed"
  const testPassRate = job.tests_total ? Math.round((job.tests_passed ?? 0) / job.tests_total * 100) : 0

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title={job.project_name ?? "Generation"} description={`Job: ${job.job_id}`}>
          <Badge
            variant={isComplete ? "success" : isFailed ? "destructive" : isRunning ? "warning" : "secondary"}
            className="text-xs"
          >
            {job.status}
          </Badge>
          {isRunning && (
            <Button variant="outline" size="sm" onClick={handleCancel}>
              <StopCircle className="mr-1 h-4 w-4" /> Cancel
            </Button>
          )}
        </PageHeader>
      </motion.div>

      {/* Progress + Message */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.1 }}
        aria-live="polite"
        aria-atomic="true"
      >
        <Card>
          <CardContent className="p-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Progress</span>
                <span className="text-xs font-mono text-muted-foreground">{job.progress}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
                  initial={{ width: 0 }}
                  animate={{ width: `${job.progress}%` }}
                  transition={{ duration: 0.8, ease: "easeOut" }}
                />
              </div>
              {job.message && (
                <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                  {job.message}
                </p>
              )}
              {job.logs && job.logs.length > 0 && (
                <div className="mt-2 space-y-0.5 max-h-20 overflow-y-auto rounded-md bg-muted/50 p-2">
                  {job.logs.slice(-5).map((log, i) => (
                    <p key={i} className="text-[10px] font-mono text-muted-foreground/70">{log}</p>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Main content */}
        <div className="lg:col-span-3 space-y-6">
          {/* Agent Pipeline */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
                Agent Pipeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <AgentPipeline agents={job.agents} />
            </CardContent>
          </Card>

          {/* Code Viewer */}
          {selectedFile && selectedContent !== undefined ? (
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
                <CodeViewer content={selectedContent} fileName={selectedFile} height={350} />
              </CardContent>
            </Card>
          ) : null}

          {/* Test Results */}
          {job.tests_total ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Bug className="h-4 w-4 text-muted-foreground" />
                  Test Results
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-6">
                  <div className="relative flex h-20 w-20 items-center justify-center">
                    <svg className="h-20 w-20 -rotate-90" viewBox="0 0 36 36">
                      <circle
                        cx="18" cy="18" r="15.5"
                        fill="none"
                        stroke="hsl(var(--muted))"
                        strokeWidth="3"
                      />
                      <motion.circle
                        cx="18" cy="18" r="15.5"
                        fill="none"
                        stroke={
                          testPassRate >= 80 ? "var(--color-success)" :
                          testPassRate >= 50 ? "var(--color-warning)" :
                          "var(--color-error)"
                        }
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeDasharray={`${testPassRate * 0.972} 97.2`}
                        initial={{ strokeDasharray: "0 97.2" }}
                        animate={{ strokeDasharray: `${testPassRate * 0.972} 97.2` }}
                        transition={{ duration: 1, ease: "easeOut" }}
                      />
                    </svg>
                    <span className="absolute text-lg font-semibold tabular-nums">{testPassRate}%</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-success" />
                      <span className="text-sm">Passed</span>
                      <span className="ml-auto text-sm font-mono tabular-nums">{job.tests_passed}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-error" />
                      <span className="text-sm">Failed</span>
                      <span className="ml-auto text-sm font-mono tabular-nums">{job.tests_failed}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-2 rounded-full bg-muted-foreground" />
                      <span className="text-sm">Total</span>
                      <span className="ml-auto text-sm font-mono tabular-nums">{job.tests_total}</span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>

        {/* Sidebar */}
        <div className="lg:col-span-2 space-y-6">
          {/* File Explorer */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-muted-foreground" />
                Generated Files
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

          {/* Actions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {isComplete && (
                <Button className="w-full" size="sm" onClick={() => router.push(`/generate/${jobId}/review`)}>
                  Review Project <ChevronRight className="ml-1 h-4 w-4" />
                </Button>
              )}
              {(isComplete || isFailed) && (
                <Button variant="outline" size="sm" className="w-full" onClick={handleDownload}>
                  <Download className="mr-2 h-4 w-4" /> Download
                </Button>
              )}
              {(isRunning || isComplete) && (
                <Button variant="outline" size="sm" className="w-full">
                  <Loader2 className="mr-2 h-4 w-4" /> Iterate
                </Button>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
