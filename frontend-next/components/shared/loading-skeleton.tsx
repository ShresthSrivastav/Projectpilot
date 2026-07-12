import { cn } from "@/lib/utils/cn"

interface SkeletonCardProps {
  className?: string
  count?: number
}

export function SkeletonCard({ className, count = 1 }: SkeletonCardProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={cn("rounded-lg border border-border bg-card p-6", className)}>
          <div className="shimmer-bg h-4 w-1/3 rounded mb-3" />
          <div className="shimmer-bg h-8 w-1/2 rounded mb-2" />
          <div className="shimmer-bg h-3 w-2/3 rounded" />
        </div>
      ))}
    </>
  )
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      <div className="flex gap-4">
        <div className="shimmer-bg h-4 w-1/4 rounded" />
        <div className="shimmer-bg h-4 w-1/4 rounded" />
        <div className="shimmer-bg h-4 w-1/4 rounded" />
        <div className="shimmer-bg h-4 w-1/4 rounded" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="shimmer-bg h-3 w-1/4 rounded" />
          <div className="shimmer-bg h-3 w-1/4 rounded" />
          <div className="shimmer-bg h-3 w-1/4 rounded" />
          <div className="shimmer-bg h-3 w-1/4 rounded" />
        </div>
      ))}
    </div>
  )
}

export function SkeletonChart() {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="shimmer-bg h-4 w-1/4 rounded mb-6" />
      <div className="flex items-end gap-2 h-40">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="shimmer-bg flex-1 rounded-t-md"
            style={{ height: `${30 + (i * 10) % 70}%` }}
          />
        ))}
      </div>
    </div>
  )
}
