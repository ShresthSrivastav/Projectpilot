"use client"

import { useParams, useRouter } from "next/navigation"
import { useState } from "react"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SkeletonCard } from "@/components/shared/loading-skeleton"
import { FileTree } from "@/components/shared/file-tree"
import { CodeViewer } from "@/components/shared/code-viewer"
import { useJobStatus, useJobFiles } from "@/lib/hooks/use-job-polling"
import { pipelineApi } from "@/lib/api/pipeline"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft, Download, Trash2, FileCode,
  ScrollText, FileText,
} from "lucide-react"
import { toast } from "sonner"
import { motion } from "framer-motion"
import { ConfirmDialog } from "@/components/shared/confirm-dialog"

export default function ProjectDetailPage() {
  const params = useParams()
  const router = useRouter()
  const jobId = params.jobId as string
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [selectedContent, setSelectedContent] = useState<string | undefined>(undefined)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const { data: job, isLoading } = useJobStatus(jobId)
  const { data: files } = useJobFiles(job?.job_id ?? null)

  const { data: changelog } = useQuery({
    queryKey: ["job", jobId, "changelog"],
    queryFn: () => pipelineApi.changelog(jobId),
    enabled: job?.status === "complete",
  })

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
      a.download = `${job?.project_name || jobId}.zip`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error("Download failed")
    }
  }

  const handleDelete = async () => {
    try {
      await pipelineApi.delete(jobId)
      toast.success("Project deleted")
      router.push("/history")
    } catch {
      toast.error("Failed to delete")
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Loading..." />
        <SkeletonCard count={3} />
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <PageHeader title={job?.project_name ?? "Project Detail"}>
          <Button variant="ghost" size="sm" onClick={() => router.push("/history")}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Back
          </Button>
        </PageHeader>
      </motion.div>

      {/* Status badges + metadata */}
      {job && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="flex flex-wrap items-center gap-3"
        >
          <Badge
            variant={job.status === "complete" ? "success" : job.status === "failed" ? "destructive" : "secondary"}
          >
            {job.status}
          </Badge>
          <span className="text-xs text-muted-foreground font-mono">{job.job_id}</span>
          {job.tests_total && (
            <span className="text-xs text-muted-foreground">
              {job.tests_passed}/{job.tests_total} tests passed
            </span>
          )}
        </motion.div>
      )}

      <Tabs defaultValue="files" className="space-y-4">
        <TabsList>
          <TabsTrigger value="files">
            <FileCode className="mr-1.5 h-3.5 w-3.5" />
            Files
          </TabsTrigger>
          <TabsTrigger value="changelog">
            <ScrollText className="mr-1.5 h-3.5 w-3.5" />
            Changelog
          </TabsTrigger>
          <TabsTrigger value="details">
            <FileText className="mr-1.5 h-3.5 w-3.5" />
            Details
          </TabsTrigger>
        </TabsList>

        <TabsContent value="files" className="space-y-0">
          <div className="grid gap-6 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium">File Explorer</CardTitle>
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
            <div className="lg:col-span-3">
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
                      <CodeViewer content={selectedContent} fileName={selectedFile} height={550} />
                    </CardContent>
                  </Card>
                </motion.div>
              ) : (
                <Card>
                  <CardContent className="flex flex-col items-center py-12 text-center">
                    <FileCode className="h-10 w-10 text-muted-foreground mb-3 opacity-40" />
                    <p className="text-sm text-muted-foreground">Select a file to view</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Browse files from the tree on the left
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>

          {/* Download / Delete actions */}
          {files && Object.keys(files).length > 0 && (
            <div className="flex gap-2 mt-4">
              <Button size="sm" variant="outline" onClick={handleDownload}>
                <Download className="mr-1.5 h-4 w-4" /> Download Project
              </Button>
              <Button size="sm" variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
                <Trash2 className="mr-1.5 h-4 w-4" /> Delete
              </Button>
            </div>
          )}
        </TabsContent>

        <TabsContent value="changelog">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Changelog</CardTitle>
            </CardHeader>
            <CardContent>
              {changelog ? (
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <pre className="whitespace-pre-wrap text-sm text-muted-foreground font-mono">
                    {changelog}
                  </pre>
                </div>
              ) : (
                <div className="flex flex-col items-center py-8">
                  <ScrollText className="h-8 w-8 text-muted-foreground mb-2 opacity-40" />
                  <p className="text-sm text-muted-foreground">No changelog available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="details">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Project Details</CardTitle>
            </CardHeader>
            <CardContent>
              {job ? (
                <div className="space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Job ID</span>
                    <span className="font-mono text-xs">{job.job_id}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Status</span>
                    <Badge
                      variant={job.status === "complete" ? "success" : job.status === "failed" ? "destructive" : "secondary"}
                      className="text-[10px]"
                    >
                      {job.status}
                    </Badge>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Progress</span>
                    <span>{job.progress}%</span>
                  </div>
                  {job.tests_total && (
                    <>
                      <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Tests Passed</span>
                        <span className="text-success">{job.tests_passed}/{job.tests_total}</span>
                      </div>
                    </>
                  )}
                  {job.message && (
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Message</span>
                      <span className="text-xs">{job.message}</span>
                    </div>
                  )}
                  {job.agents && (
                    <div className="pt-2">
                      <p className="text-xs text-muted-foreground mb-2">Agents</p>
                      <div className="flex flex-wrap gap-1.5">
                        {job.agents.map((a) => (
                          <Badge
                            key={a.name}
                            variant={
                              a.status === "complete" ? "success" :
                              a.status === "failed" ? "destructive" :
                              a.status === "running" ? "warning" : "secondary"
                            }
                            className="text-[10px]"
                          >
                            {a.name}: {a.status}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-4 text-center">No details available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Project"
        description="Are you sure you want to delete this project? This action cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={handleDelete}
      />
    </div>
  )
}
