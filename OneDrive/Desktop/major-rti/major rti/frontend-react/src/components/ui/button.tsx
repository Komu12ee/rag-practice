import * as React from "react"
import { Slot } from "@radix-ui/react-slot"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link' | 'amber'
  size?: 'default' | 'sm' | 'lg' | 'icon'
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'default', size = 'default', asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"

    const baseStyle = "btn"

    const variantStyles = {
      default: "btn-primary",
      destructive: "bg-[var(--red)] hover:bg-[var(--red)] opacity-90 hover:opacity-100 text-white",
      outline: "btn-outline",
      secondary: "bg-[var(--s2)] text-[var(--t1)] border border-[var(--s3)] hover:bg-[var(--s3)]",
      ghost: "btn-ghost",
      link: "text-[var(--navy)] underline hover:text-[var(--navy-hover)] bg-transparent p-0 border-none",
      amber: "btn-amber"
    }

    const sizeStyles = {
      default: "",
      sm: "btn-sm",
      lg: "px-6 py-2.5 text-[15px]",
      icon: "p-2 min-w-[28px] h-[28px] flex items-center justify-center",
    }

    return (
      <Comp
        className={`${baseStyle} ${variantStyles[variant]} ${sizeStyles[size]} ${className || ''}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
