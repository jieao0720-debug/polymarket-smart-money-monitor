/**
 * Server-safe locale primitives (NO "use client"): imported by the server layout
 * to read the cookie, and re-exported by lib/i18n.tsx for client code.
 */
export type Locale = "en" | "zh";

export const LOCALE_COOKIE = "pm_locale";

export function parseLocale(value: string | undefined | null): Locale {
  return value === "zh" ? "zh" : "en";
}
