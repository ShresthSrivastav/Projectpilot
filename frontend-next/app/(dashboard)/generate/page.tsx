"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Sparkles, Loader2 } from "lucide-react"
import { toast } from "sonner"

export default function GeneratePage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [prompt, setPrompt] = useState("")

  const onSubmit = async () => {
    if (prompt.trim().length < 10) {
      toast.error("Please describe your project in at least 10 characters")
      return
    }
    setLoading(true)
    try {
      const res = await pipelineApi.generate({
        prompt: prompt.trim(),
        project_name: "Generated Project",
        model: "cloud",
      })
      toast.success("Project generation started")
      router.push(`/generate/${res.job_id}`)
    } catch {
      toast.error("Failed to start generation")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <PageHeader title="Generate Project" description="Describe your project and let AI build it" />

      <Card>
        <CardContent className="p-6 space-y-4">
          <textarea
            rows={8}
            className="flex w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
            placeholder="Describe your project in detail...&#10;&#10;Example: Build a task management app with user authentication, drag-and-drop boards, real-time notifications, and a REST API backend. Include tests and Docker deployment."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="flex justify-between items-center">
            <span className="text-xs text-muted-foreground">{prompt.length} characters</span>
            <Button size="lg" onClick={onSubmit} disabled={loading || prompt.trim().length < 10}>
              {loading ? (
                <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
              ) : (
                <><Sparkles className="mr-2 h-4 w-4" /> Generate Project</>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
