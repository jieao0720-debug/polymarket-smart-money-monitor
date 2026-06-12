"use client";

import Link from "next/link";
import * as React from "react";
import { LanguageSwitcher } from "@/components/language-switcher";
import { useI18n, type MessageKey } from "@/lib/i18n";

const NAV: { href: string; key: MessageKey }[] = [
  { href: "/dashboard", key: "nav.dashboard" },
  { href: "/signals", key: "nav.signals" },
  { href: "/paper-trades", key: "nav.paperTrading" },
  { href: "/trading", key: "nav.walletTrading" },
  { href: "/settings", key: "nav.settings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-52 shrink-0 border-r border-border bg-surface md:block">
        <div className="px-4 py-5">
          <Link href="/dashboard" className="block">
            <div className="text-sm font-bold tracking-tight">{t("nav.brand")}</div>
            <div className="text-xs text-muted">{t("nav.brandSub")}</div>
          </Link>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              {t(item.key)}
            </Link>
          ))}
        </nav>
        <div className="mt-6 px-4">
          <LanguageSwitcher />
        </div>
        <div className="mt-4 px-4 text-[10px] leading-relaxed text-muted">
          {t("nav.disclaimer")}
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between gap-2 border-b border-border bg-surface px-4 py-2 md:hidden">
          <span className="shrink-0 text-sm font-bold">{t("nav.brand")}</span>
          <nav className="flex gap-3 overflow-x-auto text-xs">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href}
                    className="whitespace-nowrap text-muted hover:text-foreground">
                {t(item.key)}
              </Link>
            ))}
          </nav>
          <LanguageSwitcher className="shrink-0" />
        </header>
        <main className="mx-auto max-w-7xl p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
