/**
 * RiskPanel — manufacturability warnings with click-to-highlight in 3D.
 */

import { useWorkspaceStore } from "@/store/workspaceStore";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, ShieldAlert, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const SEVERITY_CONFIG = {
  HIGH: {
    icon: ShieldAlert,
    badge: "destructive" as const,
    border: "border-red-500/30",
    bg: "bg-red-500/5",
  },
  MEDIUM: {
    icon: AlertTriangle,
    badge: "default" as const,
    border: "border-amber-500/30",
    bg: "bg-amber-500/5",
  },
  LOW: {
    icon: Info,
    badge: "secondary" as const,
    border: "border-blue-500/30",
    bg: "bg-blue-500/5",
  },
};

export function RiskPanel() {
  const { risks, selectedFeatureId, selectFeature } = useWorkspaceStore();

  if (risks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center">
          <ShieldAlert className="mx-auto h-8 w-8 text-emerald-500/40 mb-2" />
          <p className="text-sm">No manufacturability risks</p>
        </div>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="space-y-2 p-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Risks
          </h3>
          <Badge variant="outline" className="text-[10px] h-5">
            {risks.length} issue{risks.length !== 1 ? "s" : ""}
          </Badge>
        </div>

        {risks.map((risk, i) => {
          const severity = risk.severity ?? "MEDIUM";
          const config = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.MEDIUM;
          const Icon = config.icon;
          const isSelected = risk.feature_id === selectedFeatureId;

          return (
            <button
              key={risk.feature_id ?? i}
              type="button"
              onClick={() => {
                if (risk.feature_id) selectFeature(risk.feature_id);
              }}
              className={cn(
                "w-full text-left rounded-md border p-2.5 transition-all",
                config.border,
                config.bg,
                isSelected && "ring-1 ring-primary/40",
              )}
            >
              <div className="flex items-start gap-2">
                <Icon className="h-4 w-4 shrink-0 mt-0.5 text-current" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1 mb-0.5">
                    <span className="text-xs font-medium text-foreground truncate">
                      {risk.type ?? "Risk"}
                    </span>
                    <Badge variant={config.badge} className="text-[9px] h-4 shrink-0">
                      {severity}
                    </Badge>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-2">
                    {risk.description ?? "---"}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </ScrollArea>
  );
}