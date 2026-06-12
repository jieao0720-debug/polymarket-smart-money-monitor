"use client";

/**
 * Local shadcn-style primitives (no CLI dependency — architecture.md §2).
 * Professional fintech dashboard styling, dark theme.
 */
import * as React from "react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------- Button
type ButtonVariant = "default" | "outline" | "ghost" | "danger" | "success";

export function Button({
  className,
  variant = "default",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "md";
}) {
  const variants: Record<ButtonVariant, string> = {
    default: "bg-accent hover:bg-accent-hover text-white",
    outline: "border border-border bg-transparent hover:bg-surface-2 text-foreground",
    ghost: "bg-transparent hover:bg-surface-2 text-muted hover:text-foreground",
    danger: "bg-no/90 hover:bg-no text-white",
    success: "bg-yes/90 hover:bg-yes text-white",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-40",
        size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-4 text-sm",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

// ---------------------------------------------------------------- Card
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-border bg-surface", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-4 pb-2", className)} {...props} />;
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold tracking-tight", className)} {...props} />;
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-4 pt-2", className)} {...props} />;
}

// ---------------------------------------------------------------- Badge
type BadgeVariant = "default" | "yes" | "no" | "warn" | "neutral" | "outline" | "accent";

export function Badge({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: BadgeVariant }) {
  const variants: Record<BadgeVariant, string> = {
    default: "bg-surface-2 text-foreground",
    yes: "bg-yes/15 text-yes border border-yes/30",
    no: "bg-no/15 text-no border border-no/30",
    warn: "bg-warn/15 text-warn border border-warn/30",
    neutral: "bg-neutral/15 text-muted border border-neutral/30",
    accent: "bg-accent/15 text-accent border border-accent/30",
    outline: "border border-border text-muted",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}

// ---------------------------------------------------------------- Skeleton
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-2", className)}
      data-testid="skeleton"
      {...props}
    />
  );
}

// ---------------------------------------------------------------- Inputs
export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-border bg-surface-2 px-3 text-sm text-foreground",
        "placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-md border border-border bg-surface-2 px-2 text-sm text-foreground",
        "focus:outline-none focus:ring-1 focus:ring-accent",
        className,
      )}
      {...props}
    />
  );
}

export function Checkbox({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className={cn("h-4 w-4 accent-blue-500 cursor-pointer", className)}
      {...props}
    />
  );
}

// ---------------------------------------------------------------- Table
export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className={cn("border-b border-border", className)} {...props} />;
}

export function TBody({ className, ...props }: React.HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn("divide-y divide-border/60", className)} {...props} />;
}

export function Tr({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("hover:bg-surface-2/50 transition-colors", className)} {...props} />;
}

export function Th({ className, ...props }: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-muted whitespace-nowrap",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2 whitespace-nowrap", className)} {...props} />;
}

// ---------------------------------------------------------------- Dialog (modal)
export function Dialog({
  open,
  onClose,
  children,
  wide = false,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 pt-12" role="dialog" aria-modal="true">
      <div className="fixed inset-0 bg-black/70" onClick={onClose} data-testid="dialog-backdrop" />
      <div
        className={cn(
          "relative z-10 w-full rounded-lg border border-border bg-surface shadow-2xl",
          wide ? "max-w-2xl" : "max-w-lg",
        )}
      >
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Drawer (right side)
export function Drawer({
  open,
  onClose,
  children,
  title,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: React.ReactNode;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <div className="fixed inset-0 bg-black/60" onClick={onClose} data-testid="drawer-backdrop" />
      <div className="fixed right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-border bg-surface shadow-2xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-border bg-surface px-4 py-3">
          <div className="text-sm font-semibold">{title}</div>
          <button onClick={onClose} className="text-muted hover:text-foreground" aria-label="Close drawer">
            ✕
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Alert
export function Alert({
  variant = "warn",
  className,
  children,
}: {
  variant?: "warn" | "danger" | "info";
  className?: string;
  children: React.ReactNode;
}) {
  const styles = {
    warn: "border-warn/40 bg-warn/10 text-warn",
    danger: "border-no/40 bg-no/10 text-no",
    info: "border-accent/40 bg-accent/10 text-foreground",
  };
  return (
    <div className={cn("rounded-md border px-3 py-2 text-xs leading-relaxed", styles[variant], className)} role="alert">
      {children}
    </div>
  );
}
