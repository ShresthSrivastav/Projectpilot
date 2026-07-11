"use client"

import { useMemo } from "react"
import dynamic from "next/dynamic"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils/cn"

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="space-y-3 p-4">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-full" style={{ width: `${50 + Math.random() * 40}%` }} />
      ))}
    </div>
  ),
})

interface CodeViewerProps {
  content: string
  language?: string
  fileName?: string
  height?: number | string
  className?: string
  readOnly?: boolean
}

function detectLanguage(fileName?: string): string {
  if (!fileName) return "plaintext"
  const ext = fileName.split(".").pop()?.toLowerCase()
  const languageMap: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    py: "python",
    css: "css",
    scss: "scss",
    json: "json",
    md: "markdown",
    html: "html",
    yaml: "yaml",
    yml: "yaml",
    toml: "plaintext",
    env: "plaintext",
    gitignore: "plaintext",
    dockerfile: "dockerfile",
    sh: "shell",
    bash: "shell",
    sql: "sql",
    graphql: "graphql",
    rs: "rust",
    go: "go",
    java: "java",
    kt: "kotlin",
    swift: "swift",
  }
  return languageMap[ext ?? ""] ?? "plaintext"
}

export function CodeViewer({
  content,
  language,
  fileName,
  height = 400,
  className,
  readOnly = true,
}: CodeViewerProps) {
  const detectedLang = useMemo(() => language ?? detectLanguage(fileName), [language, fileName])

  return (
    <div className={cn("relative rounded-lg overflow-hidden border border-border", className)}>
      {fileName && (
        <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-3 py-1.5 text-xs">
          <div className="h-2 w-2 rounded-full bg-primary/60" />
          <span className="font-mono text-muted-foreground">{fileName}</span>
          <span className="ml-auto text-[10px] text-muted-foreground/60">{detectedLang}</span>
        </div>
      )}
      <MonacoEditor
        theme="vs-dark"
        language={detectedLang}
        value={content}
        height={height}
        options={{
          readOnly,
          fontSize: 13,
          fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          lineNumbers: "on",
          renderLineHighlight: "none",
          padding: { top: 12, bottom: 12 },
          tabSize: 2,
          wordWrap: "on",
          smoothScrolling: true,
          cursorBlinking: "smooth",
          cursorSmoothCaretAnimation: "on",
          bracketPairColorization: { enabled: true },
          guides: { indentation: true, bracketPairs: true },
          overviewRulerBorder: false,
          scrollbar: {
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8,
          },
        }}
        loading={<Skeleton className="h-full w-full" />}
      />
    </div>
  )
}
