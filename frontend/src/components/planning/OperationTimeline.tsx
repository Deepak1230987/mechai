/**
 * OperationTimeline — vertical sequence of operation cards grouped by setup.
 * Click triggers 3D highlight via store.selectOperation().
 */

import { useMemo } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Clock, Wrench, AlertTriangle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface TimelineOperation {
  id: string;
  type: string;
  featureId: string;
  toolName: string;
  time: number;
  setupIndex: number;
  order: number;
  hasRisk: boolean;
}

export function OperationTimeline() {
  const { plan, selectedOperationId, selectOperation, risks } =
    useWorkspaceStore();

  const riskFeatureIds = useMemo(
    () => new Set(risks.map((r) => r.feature_id).filter(Boolean)),
    [risks],
  );

  const operations: TimelineOperation[] = useMemo(() => {
    if (!plan?.setups || !plan?.operations) return [];
    // Build lookup map: operation id → Operation
    const opMap = new Map(plan.operations.map((o) => [o.id, o]));
    // Build lookup map: tool id → Tool
    const toolMap = new Map((plan.tools ?? []).map((t) => [t.id, t]));

    const ops: TimelineOperation[] = [];
    plan.setups.forEach((setup, sIdx) => {
      (setup.operations ?? []).forEach((opId, oIdx) => {
        const op = opMap.get(opId);
        if (!op) return;
        const tool = toolMap.get(op.tool_id);
        ops.push({
          id: op.id,
          type: op.type ?? "operation",
          featureId: op.feature_id ?? "",
          toolName: tool ? `${tool.type} ∅${tool.diameter}` : op.tool_id.slice(0, 8),
          time: op.estimated_time ?? 0,
          setupIndex: sIdx,
          order: oIdx,
          hasRisk: riskFeatureIds.has(op.feature_id ?? ""),
        });
      });
    });
    return ops;
  }, [plan, riskFeatureIds]);

  // Group by setup
  const grouped = useMemo(() => {
    const map = new Map<number, TimelineOperation[]>();
    operations.forEach((op) => {
      const list = map.get(op.setupIndex) ?? [];
      list.push(op);
      map.set(op.setupIndex, list);
    });
    return Array.from(map.entries()).sort(([a], [b]) => a - b);
  }, [operations]);

  if (operations.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        No operations yet
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-3">
        {grouped.map(([setupIdx, ops]) => (
          <div key={setupIdx}>
            <div className="flex items-center gap-2 mb-2">
              <span className="h-px flex-1 bg-border" />
              <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
                Setup {setupIdx + 1}
              </span>
              <span className="h-px flex-1 bg-border" />
            </div>

            <div className="relative pl-4 space-y-1">
              {/* Timeline line */}
              <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

              {ops.map((op) => {
                const isSelected = selectedOperationId === op.id;
                return (
                  <button
                    key={op.id}
                    type="button"
                    onClick={() => selectOperation(op.id)}
                    className={cn(
                      "relative w-full text-left rounded-md border px-3 py-2 transition-colors",
                      "hover:bg-accent/50",
                      isSelected
                        ? "bg-primary/10 border-primary/40"
                        : "bg-transparent border-border/50",
                    )}
                  >
                    {/* Timeline dot */}
                    <div
                      className={cn(
                        "absolute -left-4 top-3 h-2.5 w-2.5 rounded-full border-2",
                        isSelected
                          ? "border-primary bg-primary"
                          : "border-muted-foreground/40 bg-background",
                      )}
                    />

                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-foreground truncate">
                        {op.type}
                      </span>
                      {op.hasRisk && (
                        <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
                      )}
                      <ChevronRight
                        className={cn(
                          "h-3 w-3 shrink-0 transition-transform",
                          isSelected ? "rotate-90 text-primary" : "text-muted-foreground/40",
                        )}
                      />
                    </div>

                    <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {op.toolName}
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {op.time.toFixed(1)}m
                      </span>
                    </div>

                    {op.featureId && (
                      <Badge
                        variant="outline"
                        className="mt-1 text-[9px] py-0 h-4 font-mono"
                      >
                        {op.featureId.slice(0, 12)}
                      </Badge>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
