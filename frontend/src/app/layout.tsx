import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AppShell } from "@/components/app-shell";
import { LOCALE_COOKIE, parseLocale } from "@/lib/locale";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Polymarket Smart Money Monitor",
  description:
    "Analysis tool for Polymarket smart-money positioning. Analysis signals only — not financial advice.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Locale cookie is read server-side so the first paint is already in the chosen
  // language (no hydration flash). It is a plain UI preference — never sensitive.
  const cookieStore = await cookies();
  const locale = parseLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <html lang={locale === "zh" ? "zh-CN" : "en"}>
      <body className="min-h-screen antialiased">
        <Providers initialLocale={locale}>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
