import * as React from "react"

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`relative overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800/80 animate-shimmer ${className || ''}`}
      {...props}
    />
  )
}

export { Skeleton }
