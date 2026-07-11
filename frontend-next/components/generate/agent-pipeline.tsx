"use client"

import { motion } from "framer-motion"
import { CheckCircle2, Loader2, XCircle, Clock } from "lucide-react"
import { cn } from "@/lib/utils/cn"
import { formatDuration } from "@/lib/utils/formatters"
import type { AgentStatus } from "@/lib/utils/types"

const DEFAULT_AGENTS = [
  "Requirements", "Planner", "CodeGen", "TestGen",
  "Debug", "Docs", "Validate", "Security",
]

const agentDescriptions: Record<string, string> = {
  Requirements: "Analyzing project requirements",
  Planner: "Architecting project structure",
  CodeGen: "Generating application code",
  TestGen: "Writing test suites",
  Debug: "Debugging and fixing issues",
  Docs: "Generating documentation",
  Validate: "Validating output quality",
  Security: "Running security audit",
}

interface AgentPipelineProps {
  agents?: AgentStatus[]
  className?: string
}

function AgentNode({
  name,
  status,
  duration,
  index,
  isLast,
}: {
  name: string
  status: string
  duration?: number
  index: number
  isLast: boolean
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08, duration: 0.3 }}
      className="relative"
    >
      <div
        className={cn(
          "relative flex items-center gap-4 rounded-lg border p-3 transition-all duration-300",
          status === "running"
            ? "border-primary/30 bg-gradient-to-r shadow-sm shadow-primary/5"
            : status === "complete"
            ? "border-success/20 bg-muted/30"
            : status === "failed"
            ? "border-error/20 bg-muted/30"
            : "border-border bg-muted/20"
        )}
      >
        {/* Connection line */}
        {!isLast && (
          <div className="absolute -bottom-4 left-6 h-4 w-px bg-border" />
        )}

        {/* Status icon */}
        <div className="relative shrink-0">
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full border transition-all duration-300",
              status === "running" && "border-primary/40 bg-primary/10",
              status === "complete" && "border-success/30 bg-success/10",
              status === "failed" && "border-error/30 bg-error/10",
              status === "pending" && "border-border bg-muted"
            )}
          >
            {status === "complete" ? (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 300, damping: 15 }}
              >
                <CheckCircle2 className="h-4 w-4 text-success" />
              </motion.div>
            ) : status === "running" ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : status === "failed" ? (
              <XCircle className="h-4 w-4 text-error" />
            ) : (
              <Clock className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
          {status === "running" && (
            <span className="absolute -inset-1 animate-ping rounded-full bg-primary/15" />
          )}
        </div>

        {/* Name & description */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "text-sm font-medium",
                status === "running" && "text-primary",
                status === "complete" && "text-success",
                status === "failed" && "text-error",
                status === "pending" && "text-muted-foreground"
              )}
            >
              {name}
            </span>
            {duration && (
              <span className="text-[10px] font-mono text-muted-foreground/60">
                {formatDuration(duration)}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground/70 mt-0.5">
            {agentDescriptions[name] ?? "Processing..."}
          </p>
        </div>

        {/* Status badge */}
        <div
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium capitalize",
            status === "complete" && "bg-success/10 text-success",
            status === "running" && "bg-primary/10 text-primary",
            status === "failed" && "bg-error/10 text-error",
            status === "pending" && "bg-muted text-muted-foreground"
          )}
        >
          {status}
        </div>
      </div>
    </motion.div>
  )
}

export function AgentPipeline({ agents, className }: AgentPipelineProps) {
  const completedCount = agents?.filter((a) => a.status === "complete").length ?? 0

  return (
    <div className={cn("space-y-4", className)}>
      {/* Summary bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-primary to-accent"
            initial={{ width: 0 }}
            animate={{ width: `${agents ? (completedCount / agents.length) * 100 : 0}%` }}
            transition={{ duration: 0.5, ease: "easeOut" }}
          />
        </div>
        <span className="text-xs text-muted-foreground tabular-nums shrink-0">
          {completedCount}/{agents?.length ?? DEFAULT_AGENTS.length}
        </span>
      </div>

      {/* Agent nodes */}
      <div className="space-y-3">
        {(agents ?? []).map((agent, i) => (
          <AgentNode
            key={agent.name}
            name={agent.name}
            status={agent.status}
            duration={agent.duration}
            index={i}
            isLast={i === (agents?.length ?? 0) - 1}
          />
        ))}
      </div>
    </div>
  )
}
