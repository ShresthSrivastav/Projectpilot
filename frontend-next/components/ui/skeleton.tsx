import { cn } from "@/lib/utils/cn"

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-md shimmer-bg", className)}
      {...props}
    />
  )
}

export { Skeleton }
