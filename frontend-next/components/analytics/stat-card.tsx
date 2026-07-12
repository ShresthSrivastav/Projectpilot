"use client"

import { useEffect, useRef, useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils/cn"
import { motion } from "framer-motion"

interface StatCardProps {
  label: string
  value: number | string
  icon: React.ElementType
  color?: string
  trend?: { value: number; positive: boolean }
  formatter?: (value: number) => string
  className?: string
}

export function StatCard({
  label,
  value,
  icon: Icon,
  color = "text-primary",
  trend,
  formatter,
  className,
}: StatCardProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const prevValue = useRef(0)
  const numericValue = typeof value === "number" ? value : 0

  useEffect(() => {
    const duration = 600
    const steps = 20
    const increment = (numericValue - prevValue.current) / steps
    let current = prevValue.current
    let step = 0

    const timer = setInterval(() => {
      step++
      current += increment
      if (step >= steps) {
        setDisplayValue(numericValue)
        prevValue.current = numericValue
        clearInterval(timer)
      } else {
        setDisplayValue(Math.round(current))
      }
    }, duration / steps)

    return () => clearInterval(timer)
  }, [numericValue])

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card className={cn("overflow-hidden", className)}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">{label}</span>
            <Icon className={cn("h-4 w-4", color)} />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tracking-tight">
              {typeof value === "number" ? (formatter ? formatter(displayValue) : displayValue.toLocaleString()) : value}
            </span>
            {trend && (
              <span
                className={cn(
                  "text-xs font-medium",
                  trend.positive ? "text-success" : "text-error"
                )}
              >
                {trend.positive ? "+" : ""}{trend.value}%
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}
