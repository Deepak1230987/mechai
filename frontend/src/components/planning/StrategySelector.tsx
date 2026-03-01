/**
 * StrategySelector — comparison table of machining strategies.
 * Click to select, triggers live cost/time recalculation.
 */

import { useStrategy } from "@/hooks/useStrategy";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Clock, Zap } from "lucide-react";

export function StrategySelector() {
  const { strategies, selectedStrategy, selectStrategy } = useStrategy();

  if (strategies.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        No strategies available
      </div>
    );
  }

  return (
    <div className="space-y-2 p-3">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
        Strategy Selection
      </h3>
      {strategies.map((s) => {
        const isActive = selectedStrategy === s.name;
        return (
          <button
            key={s.name}
            type="button"
            onClick={() => selectStrategy(s.name)}
            className={cn(
              "w-full text-left rounded-lg border p-3 transition-all",
              isActive
                ? "border-primary bg-primary/8 ring-1 ring-primary/30"
                : "border-border/50 bg-transparent hover:bg-accent/40",
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-foreground">
                {s.name}
              </span>
              {isActive && (
                <Badge variant="default" className="text-[10px] h-5">
                  <Zap className="h-3 w-3 mr-1" />
                  Active
                </Badge>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {s.estimated_time?.toFixed(1) ?? "—"}m
              </span>
            </div>

            {s.description && (
              <p className="mt-2 text-[10px] text-muted-foreground/70 line-clamp-2">
                {s.description}
              </p>
            )}
          </button>
        );
      })}
    </div>
  );
}
