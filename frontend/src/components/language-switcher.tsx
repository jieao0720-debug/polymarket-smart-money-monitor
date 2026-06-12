"use client";

import { useI18n, type Locale } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "zh", label: "中文" },
];

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale } = useI18n();
  return (
    <div
      className={cn("inline-flex overflow-hidden rounded-md border border-border", className)}
      role="group"
      aria-label="Language / 语言"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          onClick={() => setLocale(option.value)}
          aria-pressed={locale === option.value}
          className={cn(
            "px-2.5 py-1 text-xs font-medium transition-colors",
            locale === option.value
              ? "bg-accent text-white"
              : "bg-surface-2 text-muted hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
