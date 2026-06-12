"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatUsd } from "@/lib/format";

export function SmartMoneyNotionalChart({
  yesNotional,
  noNotional,
}: {
  yesNotional: number;
  noNotional: number;
}) {
  const data = [
    { side: "YES smart $", value: yesNotional, fill: "#10b981" },
    { side: "NO smart $", value: noNotional, fill: "#ef4444" },
  ];
  return (
    <div className="h-44 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 16, right: 24, top: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#232f48" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#8b97ad", fontSize: 11 }}
            tickFormatter={(v: number) => formatUsd(v)}
            stroke="#232f48"
          />
          <YAxis type="category" dataKey="side" tick={{ fill: "#8b97ad", fontSize: 11 }} width={90} stroke="#232f48" />
          <Tooltip
            cursor={{ fill: "rgba(59,130,246,0.06)" }}
            contentStyle={{ background: "#111827", border: "1px solid #232f48", borderRadius: 8, fontSize: 12 }}
            formatter={(value) => [formatUsd(Number(value), 2), "smart money notional"]}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
