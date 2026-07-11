"use client"

import { Button } from "@/components/ui/button"
import { ExternalLink, Book } from "lucide-react"
import type { GitHubRepo } from "@/lib/utils/types"

const languageColors: Record<string, string> = {
  TypeScript: "bg-blue-500",
  JavaScript: "bg-yellow-400",
  Python: "bg-emerald-500",
  Rust: "bg-orange-600",
  Go: "bg-cyan-500",
  Java: "bg-red-500",
  Kotlin: "bg-purple-500",
  Swift: "bg-orange-500",
  Ruby: "bg-red-600",
  CSS: "bg-purple-400",
  HTML: "bg-orange-500",
  Shell: "bg-green-600",
  Dockerfile: "bg-blue-400",
  "C++": "bg-pink-600",
  C: "bg-gray-500",
}

interface RepoCardProps {
  repo: GitHubRepo
  onSelect: (repo: GitHubRepo) => void
}

export function RepoCard({ repo, onSelect }: RepoCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3 hover:bg-muted/50 transition-colors group">
      <Book className="h-5 w-5 text-muted-foreground mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium truncate group-hover:text-primary transition-colors">
            {repo.full_name}
          </span>
          <a
            href={repo.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ExternalLink className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
          </a>
        </div>
        {repo.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{repo.description}</p>
        )}
        <div className="flex items-center gap-3 mt-2">
          {repo.language && (
            <div className="flex items-center gap-1.5">
              <div className={`h-2.5 w-2.5 rounded-full ${languageColors[repo.language] ?? "bg-muted-foreground"}`} />
              <span className="text-[11px] text-muted-foreground">{repo.language}</span>
            </div>
          )}
          <span className="text-[11px] text-muted-foreground">
            Updated {repo.updated_at ? new Date(repo.updated_at).toLocaleDateString() : ""}
          </span>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={() => onSelect(repo)}
      >
        Select
      </Button>
    </div>
  )
}
