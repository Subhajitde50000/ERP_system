import { GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";

/** shikshasync.me wordmark — light variant for the dark panel, dark for white surfaces. */
export function Logo({
  variant = "dark",
  className,
}: {
  variant?: "light" | "dark";
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-xl",
          variant === "light" ? "bg-white" : "bg-primary",
        )}
      >
        <GraduationCap
          className={cn(
            "h-5 w-5",
            variant === "light" ? "text-primary" : "text-white",
          )}
          aria-hidden="true"
        />
      </div>
      <span
        className={cn(
          "font-display text-xl font-bold tracking-tight",
          variant === "light" ? "text-white" : "text-primary",
        )}
      >
        shikshasync.me
      </span>
    </div>
  );
}
