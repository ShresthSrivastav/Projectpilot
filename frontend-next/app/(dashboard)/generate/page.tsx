"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { generateSchema, type GenerateFormData, stackConfigSchema, type StackConfig } from "@/lib/utils/validators"
import { pipelineApi } from "@/lib/api/pipeline"
import { PageHeader } from "@/components/shared/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sparkles, Loader2, HelpCircle } from "lucide-react"
import { toast } from "sonner"

const stackFields: { key: keyof StackConfig; label: string; options: { value: string; label: string }[] }[] = [
  { key: "backend", label: "Backend", options: [{ value: "fastapi", label: "FastAPI" }, { value: "flask", label: "Flask" }, { value: "express", label: "Express" }, { value: "none", label: "None" }] },
  { key: "frontend", label: "Frontend", options: [{ value: "react", label: "React" }, { value: "vue", label: "Vue" }, { value: "streamlit", label: "Streamlit" }, { value: "none", label: "None" }] },
  { key: "db", label: "Database", options: [{ value: "sqlite", label: "SQLite" }, { value: "postgresql", label: "PostgreSQL" }, { value: "mysql", label: "MySQL" }, { value: "none", label: "None" }] },
  { key: "css", label: "CSS", options: [{ value: "tailwind", label: "Tailwind" }, { value: "bootstrap", label: "Bootstrap" }, { value: "none", label: "None" }] },
  { key: "testing", label: "Testing", options: [{ value: "pytest", label: "pytest" }, { value: "jest", label: "Jest" }, { value: "none", label: "None" }] },
  { key: "auth", label: "Auth", options: [{ value: "jwt", label: "JWT" }, { value: "none", label: "None" }] },
]

export default function GeneratePage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [stack, setStack] = useState<StackConfig>(stackConfigSchema.parse({}))
  const [clarifyQuestion, setClarifyQuestion] = useState<string | null>(null)

  const { register, handleSubmit, watch, formState: { errors } } = useForm<GenerateFormData>({
    resolver: zodResolver(generateSchema),
  })

  const prompt = watch("prompt", "") // eslint-disable-line react-hooks/incompatible-library

  const handleClarify = async () => {
    if (prompt.length < 10) return
    try {
      const res = await pipelineApi.clarify({ prompt, model: "cloud" })
      if (res.question) setClarifyQuestion(res.question)
    } catch {
      // ignore
    }
  }

  const onSubmit = async (data: GenerateFormData) => {
    setLoading(true)
    try {
      const res = await pipelineApi.generate({
        prompt: data.prompt,
        project_name: data.projectName,
        model: data.model ?? "cloud",
        stack: stack as unknown as Record<string, string>,
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
        <CardHeader>
          <CardTitle>Project Details</CardTitle>
          <CardDescription>Tell us what you want to build</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="projectName">Project Name</Label>
            <Input id="projectName" placeholder="My API" {...register("projectName")} />
            {errors.projectName && <p className="text-xs text-error">{errors.projectName.message}</p>}
          </div>

          <div className="space-y-2">
            <Label htmlFor="prompt">Prompt</Label>
            <textarea
              id="prompt"
              rows={5}
              className="flex w-full rounded-md border border-border bg-transparent px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring resize-none"
              placeholder="Describe your project in detail..."
              {...register("prompt")}
            />
            {errors.prompt && <p className="text-xs text-error">{errors.prompt.message}</p>}
            <div className="flex justify-between">
              <span className="text-xs text-muted-foreground">{prompt.length}/500</span>
              <Button variant="ghost" size="sm" className="text-xs" onClick={handleClarify} type="button">
                <HelpCircle className="mr-1 h-3 w-3" />
                Clarify
              </Button>
            </div>
            {clarifyQuestion && (
              <div className="rounded-md bg-muted p-3 text-sm">{clarifyQuestion}</div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stack Configuration</CardTitle>
          <CardDescription>Choose your technology stack</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            {stackFields.map((field) => (
              <div key={field.key} className="space-y-1.5">
                <Label className="text-xs">{field.label}</Label>
                <Select
                  value={stack[field.key]}
                  onValueChange={(value) => setStack((prev) => ({ ...prev, [field.key]: value }))}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {field.options.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value} className="text-xs">
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Button size="lg" className="w-full" onClick={handleSubmit(onSubmit)} disabled={loading}>
        {loading ? (
          <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating...</>
        ) : (
          <><Sparkles className="mr-2 h-4 w-4" /> Generate Project</>
        )}
      </Button>
    </div>
  )
}
