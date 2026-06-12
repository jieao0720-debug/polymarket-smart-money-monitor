import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataState } from "@/components/common";
import { formatCents, formatUsd, shortAddress } from "@/lib/format";

describe("DataState", () => {
  it("shows the loading skeleton state", () => {
    render(<DataState loading error={null} />);
    expect(screen.getByTestId("loading-state")).toBeInTheDocument();
    expect(screen.getAllByTestId("skeleton").length).toBeGreaterThan(0);
  });

  it("shows the error state with the message", () => {
    render(<DataState loading={false} error={new Error("backend unreachable")} />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByText(/backend unreachable/)).toBeInTheDocument();
  });

  it("shows the empty state with a hint", () => {
    render(<DataState loading={false} error={null} empty emptyHint="Run the scanner first" />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("Run the scanner first")).toBeInTheDocument();
  });

  it("renders children when data is present", () => {
    render(
      <DataState loading={false} error={null} empty={false}>
        <div>content</div>
      </DataState>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});

describe("format helpers", () => {
  it("shortens addresses without mangling them", () => {
    expect(shortAddress("0x" + "ab".repeat(20))).toBe("0xabab…abab");
  });

  it("formats prices as cents on the 0-1 scale", () => {
    expect(formatCents(0.615)).toBe("61.5¢");
    expect(formatCents(null)).toBe("—");
  });

  it("formats usd compactly", () => {
    expect(formatUsd(1_250_000)).toBe("$1.3M");
    expect(formatUsd(25_500)).toBe("$25.5k");
    expect(formatUsd(42, 2)).toBe("$42");
  });
});
