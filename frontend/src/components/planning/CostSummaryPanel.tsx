/**
 * CostSummaryPanel — total time/cost display with Recharts breakdown chart.
 * Auto-updates when strategy changes.
 */

import { useMemo } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Clock, DollarSign, Gauge } from "lucide-react";

const CHART_COLORS = [
  "#2563eb", // blue
  "#14b8a6", // teal
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#10b981", // emerald
  "#f97316", // orange
];

export function CostSummaryPanel() {
  const { cost, time } = useWorkspaceStore();

  const costPieData = useMemo(() => {
    if (!cost) return [];
    const entries: { name: string; value: number }[] = [];
    if (cost.material_cost) entries.push({ name: "Material", value: cost.material_cost });
    if (cost.machining_cost) entries.push({ name: "Machining", value: cost.machining_cost });
    if (cost.tooling_cost) entries.push({ name: "Tooling", value: cost.tooling_cost });
    if (cost.setup_cost) entries.push({ name: "Setup", value: cost.setup_cost });
    if (cost.overhead_cost) entries.push({ name: "Overhead", value: cost.overhead_cost });
    return entries;
  }, [cost]);

  const complexityScore = time?.complexity_score ?? null;

  const complexityColor = useMemo(() => {
    if (!complexityScore) return "secondary";
    if (complexityScore >= 8) return "destructive";
    if (complexityScore >= 5) return "default";
    return "secondary";
  }, [complexityScore]);

  return (
    <div className="space-y-3 p-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Cost &amp; Time Summary
      </h3>

      {/* Headline stats */}
      <div className="grid grid-cols-3 gap-2">
        <StatCard
          icon={<Clock className="h-4 w-4 text-blue-400" />}
          label="Total Time"
          value={time ? `${time.total_time?.toFixed(1)}m` : "—"}
        />
        <StatCard
          icon={<DollarSign className="h-4 w-4 text-emerald-400" />}
          label="Total Cost"
          value={cost ? `$${cost.total_cost?.toFixed(2)}` : "—"}
        />
        <StatCard
          icon={<Gauge className="h-4 w-4 text-amber-400" />}
          label="Complexity"
          value={
            complexityScore != null ? (
              <Badge variant={complexityColor as "default"} className="text-[10px] h-5">
                {complexityScore.toFixed(1)}/10
              </Badge>
            ) : (
              "—"
            )
          }
        />
      </div>

      {/* Cost breakdown chart */}
      {costPieData.length > 0 && (
        <div className="flex items-center gap-4">
          <div className="w-24 h-24 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={costPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={20}
                  outerRadius={38}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {costPieData.map((_entry, i) => (
                    <Cell
                      key={i}
                      fill={CHART_COLORS[i % CHART_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                    color: "hsl(var(--foreground))",
                  }}
                  formatter={(value) => [`$${Number(value).toFixed(2)}`, ""]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="flex-1 space-y-1">
            {costPieData.map((entry, i) => (
              <div key={entry.name} className="flex items-center justify-between text-[11px]">
                <span className="flex items-center gap-1.5">
                  <span
                    className="h-2 w-2 rounded-full shrink-0"
                    style={{
                      backgroundColor: CHART_COLORS[i % CHART_COLORS.length],
                    }}
                  />
                  <span className="text-muted-foreground">{entry.name}</span>
                </span>
                <span className="font-mono text-foreground">
                  ${entry.value.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Time breakdown */}
      {time && (
        <div className="space-y-1 pt-1 border-t border-border/50">
          <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1">
            Time Breakdown
          </p>
          <TimeRow label="Cutting" value={time.total_cutting_time} />
          <TimeRow label="Setup" value={time.total_setup_time} />
          <TimeRow label="Tool Changes" value={time.total_tool_change_time} />
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-border/50 bg-muted/20 p-2 text-center">
      <div className="flex justify-center mb-1">{icon}</div>
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="text-sm font-semibold text-foreground mt-0.5">{value}</p>
    </div>
  );
}

function TimeRow({ label, value }: { label: string; value?: number }) {
  if (value == null) return null;
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground">{value.toFixed(1)}m</span>
    </div>
  );
}
