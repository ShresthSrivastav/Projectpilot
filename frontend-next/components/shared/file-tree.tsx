"use client"

import { useState, useMemo } from "react"
import { cn } from "@/lib/utils/cn"
import { File, Folder, FolderOpen, ChevronRight, ChevronDown } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"

interface TreeNode {
  name: string
  path: string
  type: "file" | "folder"
  children: TreeNode[]
  content?: string
}

function buildTree(files: Record<string, string>): TreeNode[] {
  const root: TreeNode[] = []

  for (const [filePath, content] of Object.entries(files)) {
    const parts = filePath.replace(/^\/+/, "").split("/")
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isFile = i === parts.length - 1
      const existing = current.find((n) => n.name === part)

      if (existing) {
        if (isFile) existing.content = content
        current = existing.children
      } else {
        const node: TreeNode = {
          name: part,
          path: parts.slice(0, i + 1).join("/"),
          type: isFile ? "file" : "folder",
          children: [],
          content: isFile ? content : undefined,
        }
        current.push(node)
        current = node.children
      }
    }
  }

  return root.sort((a, b) => {
    if (a.type !== b.type) return a.type === "folder" ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

function getFileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase()
  const iconMap: Record<string, string> = {
    ts: "bg-blue-500/20 text-blue-400",
    tsx: "bg-sky-500/20 text-sky-400",
    js: "bg-yellow-500/20 text-yellow-400",
    jsx: "bg-orange-500/20 text-orange-400",
    py: "bg-emerald-500/20 text-emerald-400",
    css: "bg-purple-500/20 text-purple-400",
    scss: "bg-pink-500/20 text-pink-400",
    json: "bg-neutral-500/20 text-neutral-400",
    md: "bg-gray-500/20 text-gray-400",
    html: "bg-red-500/20 text-red-400",
    yaml: "bg-amber-500/20 text-amber-400",
    yml: "bg-amber-500/20 text-amber-400",
    toml: "bg-rose-500/20 text-rose-400",
    gitignore: "bg-stone-500/20 text-stone-400",
    env: "bg-lime-500/20 text-lime-400",
  }
  return iconMap[ext ?? ""] ?? "bg-muted text-muted-foreground"
}

interface FileTreeNodeProps {
  node: TreeNode
  depth: number
  selectedPath: string | null
  onSelect: (path: string, content?: string) => void
}

function FileTreeNode({ node, depth, selectedPath, onSelect }: FileTreeNodeProps) {
  const [expanded, setExpanded] = useState(depth < 1)
  const isSelected = selectedPath === node.path

  if (node.type === "file") {
    return (
      <button
        onClick={() => onSelect(node.path, node.content)}
        className={cn(
          "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors",
          isSelected
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:bg-muted hover:text-foreground"
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        <div className={cn("flex h-4 w-4 items-center justify-center rounded", getFileIcon(node.name))}>
          <File className="h-2.5 w-2.5" />
        </div>
        <span className="truncate font-mono">{node.name}</span>
      </button>
    )
  }

  return (
    <div>
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs transition-colors",
          "text-muted-foreground hover:bg-muted hover:text-foreground"
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        {expanded ? (
          <FolderOpen className="h-3.5 w-3.5 text-accent shrink-0" />
        ) : (
          <Folder className="h-3.5 w-3.5 text-primary/70 shrink-0" />
        )}
        <span className="truncate font-medium">{node.name}</span>
        <span className="ml-auto text-[10px] text-muted-foreground/60">{node.children.length}</span>
      </button>
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                depth={depth + 1}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

interface FileTreeProps {
  files: Record<string, string> | null | undefined
  selectedPath?: string | null
  onSelect?: (path: string, content?: string) => void
  className?: string
}

export function FileTree({ files, selectedPath, onSelect, className }: FileTreeProps) {
  const tree = useMemo(() => (files ? buildTree(files) : []), [files])

  if (!files) {
    return (
      <div className="space-y-1 p-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-5 rounded animate-pulse bg-muted" style={{ marginLeft: i * 12 }} />
        ))}
      </div>
    )
  }

  if (tree.length === 0) {
    return (
      <div className="flex flex-col items-center py-8 text-center">
        <Folder className="h-6 w-6 text-muted-foreground mb-2 opacity-40" />
        <p className="text-xs text-muted-foreground">No files</p>
      </div>
    )
  }

  return (
    <div className={cn("space-y-0.5", className)}>
      {tree.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath ?? null}
          onSelect={onSelect ?? (() => {})}
        />
      ))}
    </div>
  )
}
