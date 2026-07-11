"use client"

import { motion } from "framer-motion"
import { cn } from "@/lib/utils/cn"

interface ThinkingIndicatorProps {
  className?: string
}

export function ThinkingIndicator({ className }: ThinkingIndicatorProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      role="status"
      aria-live="polite"
      className={cn("flex items-start gap-3", className)}
    >
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-primary/60"
              animate={{
                y: ["0%", "-60%", "0%"],
                opacity: [0.4, 1, 0.4],
              }}
              transition={{
                duration: 1.2,
                repeat: Infinity,
                delay: i * 0.2,
                ease: "easeInOut",
              }}
            />
          ))}
        </div>
      </div>
      <div className="flex-1 space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Assistant</span>
          <span className="text-[10px] text-muted-foreground/50">thinking...</span>
        </div>
        <div className="space-y-1.5">
          {[40, 65, 30].map((w, i) => (
            <motion.div
              key={i}
              className="h-2.5 rounded-full bg-muted"
              initial={{ width: 0 }}
              animate={{ width: `${w}%` }}
              transition={{
                duration: 0.8,
                delay: i * 0.3,
                repeat: Infinity,
                repeatDelay: 2,
              }}
              style={{ width: `${w}%` }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  )
}
