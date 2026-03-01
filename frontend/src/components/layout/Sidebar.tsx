/**
 * WorkspaceSidebar — compact sidebar for the ModelWorkspace page.
 * Shows model info, navigation, status indicators, and export actions.
 */

import { Link } from "react-router-dom";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Box,
  ArrowLeft,
  Activity,
  Layers,
  Clock,
  DollarSign,
  AlertTriangle,
  GitBranch,
  FileText,
  Download,
  Loader2,
  CheckCircle,
  Settings,
} from "lucide-react";

interface WorkspaceSidebarProps {
  onExportPDF: () => void;
  isExporting: boolean;
}

const STAGE_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: "Ready", color: "text-emerald-400" },
  analyzing_geometry: { label: "Analyzing Geometry", color: "text-blue-400" },
  generating_plan: { label: "Generating Plan", color: "text-amber-400" },
  optimizing: { label: "Optimizing", color: "text-purple-400" },
  generating_pdf: { label: "Generating PDF", color: "text-cyan-400" },
  submitting_rfq: { label: "Submitting RFQ", color: "text-orange-400" },
  simulating_impact: { label: "Simulating Impact", color: "text-rose-400" },
};

export function WorkspaceSidebar({
  onExportPDF,
  isExporting,
}: WorkspaceSidebarProps) {
  const {
    modelId,
    modelName,
    plan,
    cost,
    time,
    risks,
    versionHistory,
    processingStage,
  } = useWorkspaceStore();

  const stage = STAGE_LABELS[processingStage] ?? STAGE_LABELS.idle;

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      {/* Header */}
      <div className="flex h-14 items-center border-b border-sidebar-border px-4">
        <Link
          to={modelId ? `/models/${modelId}` : "/models"}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back</span>
        </Link>
      </div>

      {/* Model Info */}
      <div className="px-4 py-3 border-b border-sidebar-border">
        <div className="flex items-center gap-2 mb-1">
          <Box className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold truncate">
            {modelName || "Model"}
          </span>
        </div>
        {plan && (
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-[10px] h-5">
              v{plan.version}
            </Badge>
            <Badge
              variant={plan.approved ? "default" : "secondary"}
              className="text-[10px] h-5"
            >
              {plan.approved ? "Approved" : "Draft"}
            </Badge>
          </div>
        )}
      </div>

      {/* Status Indicator */}
      <div className="px-4 py-2 border-b border-sidebar-border">
        <div className="flex items-center gap-2">
          {processingStage === "idle" ? (
            <CheckCircle className={cn("h-3 w-3", stage.color)} />
          ) : (
            <Loader2 className={cn("h-3 w-3 animate-spin", stage.color)} />
          )}
          <span className={cn("text-[11px] font-medium", stage.color)}>
            {stage.label}
          </span>
        </div>
        {processingStage !== "idle" && (
          <div className="mt-1.5 h-1 w-full rounded-full bg-sidebar-accent overflow-hidden">
            <div className="h-full w-1/2 rounded-full bg-primary animate-pulse" />
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        <p className="px-2 mb-2 text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
          Plan Summary
        </p>

        <StatRow
          icon={Layers}
          label="Setups"
          value={plan?.setups?.length ?? 0}
        />
        <StatRow
          icon={Activity}
          label="Operations"
          value={plan?.operations?.length ?? 0}
        />
        <StatRow
          icon={Clock}
          label="Total Time"
          value={time ? `${time.total_time_minutes.toFixed(1)}m` : "—"}
        />
        <StatRow
          icon={DollarSign}
          label="Total Cost"
          value={cost ? `$${cost.total_cost.toFixed(2)}` : "—"}
        />
        <StatRow
          icon={AlertTriangle}
          label="Risks"
          value={risks.length}
          highlight={risks.length > 0}
        />
        <StatRow
          icon={GitBranch}
          label="Versions"
          value={versionHistory.length}
        />

        <Separator className="my-3 opacity-30" />

        <p className="px-2 mb-2 text-[10px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
          Actions
        </p>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="w-full justify-start gap-2 text-xs"
              onClick={onExportPDF}
              disabled={isExporting || !plan}
            >
              {isExporting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              Download Report
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            <p>Download full manufacturing PDF report</p>
          </TooltipContent>
        </Tooltip>
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-4 py-2">
        <div className="flex items-center gap-2 text-[10px] text-sidebar-foreground/30">
          <Settings className="h-3 w-3" />
          <span>MechAI Workspace</span>
        </div>
      </div>
    </div>
  );
}

// ─── Stat Row ────────────────────────────────────────────────────────────────

function StatRow({
  icon: Icon,
  label,
  value,
  highlight = false,
}: {
  icon: typeof FileText;
  label: string;
  value: string | number;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-md px-2 py-1.5 text-xs">
      <div className="flex items-center gap-2 text-sidebar-foreground/60">
        <Icon className="h-3.5 w-3.5" />
        <span>{label}</span>
      </div>
      <span
        className={cn(
          "font-medium tabular-nums",
          highlight ? "text-amber-400" : "text-sidebar-foreground",
        )}
      >
        {value}
      </span>
    </div>
  );
}
