import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LanguageSwitcher } from "@/components/language-switcher";
import { I18nProvider, translate, translateBlocker, useI18n } from "@/lib/i18n";

function Probe() {
  const { t, locale } = useI18n();
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="label">{t("nav.dashboard")}</span>
    </div>
  );
}

describe("translate", () => {
  it("returns english and chinese variants", () => {
    expect(translate("en", "nav.dashboard")).toBe("Dashboard");
    expect(translate("zh", "nav.dashboard")).toBe("仪表盘");
  });

  it("interpolates params", () => {
    expect(translate("en", "dash.errors", { n: 3 })).toBe("3 errors");
    expect(translate("zh", "dash.scanCount", { analyzed: 2, found: 10 })).toBe("2/10 个市场");
  });

  it("keeps the mandated safety statement verbatim in english", () => {
    expect(translate("en", "modal.manualStatement")).toBe(
      "This is not automated trading. You are manually confirming this order.",
    );
    // zh variant must still carry the English original for compliance
    expect(translate("zh", "modal.manualStatement")).toContain(
      "This is not automated trading",
    );
  });
});

describe("translateBlocker", () => {
  it("passes english through unchanged", () => {
    expect(translateBlocker("en", "Wallet is not connected.")).toBe("Wallet is not connected.");
  });

  it("translates known blockers to chinese", () => {
    expect(translateBlocker("zh", "Wallet is not connected.")).toBe("钱包未连接。");
  });

  it("translates the prefixed risk-check blocker and keeps the backend reason", () => {
    const result = translateBlocker("zh", "Backend risk check failed: spread too wide");
    expect(result).toContain("后端风控检查未通过");
    expect(result).toContain("spread too wide");
  });

  it("passes unknown strings through untouched", () => {
    expect(translateBlocker("zh", "some backend message")).toBe("some backend message");
  });
});

describe("I18nProvider + LanguageSwitcher", () => {
  it("defaults components to english without a provider", () => {
    render(<Probe />);
    expect(screen.getByTestId("label")).toHaveTextContent("Dashboard");
  });

  it("renders the initial locale and switches on click", () => {
    render(
      <I18nProvider initialLocale="en">
        <LanguageSwitcher />
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId("label")).toHaveTextContent("Dashboard");

    fireEvent.click(screen.getByRole("button", { name: "中文" }));
    expect(screen.getByTestId("locale")).toHaveTextContent("zh");
    expect(screen.getByTestId("label")).toHaveTextContent("仪表盘");
    expect(document.cookie).toContain("pm_locale=zh");

    fireEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByTestId("label")).toHaveTextContent("Dashboard");
  });
});
