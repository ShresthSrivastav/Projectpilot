"use client"

import { useQuery, useQueryClient } from "@tanstack/react-query"
import { pipelineApi } from "@/lib/api/pipeline"
import { POLL_INTERVAL } from "@/lib/utils/constants"
import { useState, useCallback } from "react"

export function useJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId, "status"],
    queryFn: () => pipelineApi.status(jobId!),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "running" || status === "queued" ? POLL_INTERVAL : false
    },
  })
}

export function useJobFiles(jobId: string | null) {
  const [fileContent, setFileContent] = useState<Record<string, string>>({})
  const queryClient = useQueryClient()

  const filesQuery = useQuery({
    queryKey: ["job", jobId, "files"],
    queryFn: () => pipelineApi.files(jobId!),
    enabled: !!jobId,
    refetchInterval: () => {
      if (!jobId) return false
      const jobState = queryClient.getQueryState(["job", jobId, "status"])
      const status = (jobState?.data as { status?: string })?.status
      return status === "running" || status === "queued" ? 3000 : false
    },
  })

  const loadFileContent = useCallback(async (filePath: string) => {
    if (!jobId) return
    if (fileContent[filePath]) return
    try {
      const { content } = await pipelineApi.readFile(jobId, filePath)
      setFileContent((prev) => ({ ...prev, [filePath]: content }))
    } catch {
      setFileContent((prev) => ({ ...prev, [filePath]: "// Error loading file content" }))
    }
  }, [jobId, fileContent])

  const fileTree: Record<string, string> | null = Array.isArray(filesQuery.data)
    ? Object.fromEntries(filesQuery.data.map((p: string) => [p, fileContent[p] ?? ""]))
    : null

  return {
    data: fileTree,
    isLoading: filesQuery.isLoading,
    error: filesQuery.error,
    loadFileContent,
    hasLoaded: (path: string) => !!fileContent[path],
  }
}

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: () => pipelineApi.jobs(),
  })
}
