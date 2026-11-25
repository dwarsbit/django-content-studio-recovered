import { cn } from "@/lib/utils";

/** A placeholder block that pulses while its content loads. */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn(
        "bg-foreground/8 rounded-md animate-pulse motion-reduce:animate-none",
        className,
      )}
      {...props}
    />
  );
}
