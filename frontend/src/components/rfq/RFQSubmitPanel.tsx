/**
 * RFQSubmitPanel — Request for Quote summary + submission.
 */

import { useState } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { generateRFQ } from "@/lib/intelligence-api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Clock,
  DollarSign,
  FileText,
  Layers,
  Send,
  CheckCircle2,
  Loader2,
} from "lucide-react";

export function RFQSubmitPanel() {
  const { modelId, cost, time, plan, selectedStrategy } = useWorkspaceStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!modelId) return;
    setIsSubmitting(true);
    try {
      await generateRFQ(modelId, {
        quantity: 1,
      });
      setSubmitted(true);
    } catch {
      // Error handled silently — could add toast
    } finally {
      setIsSubmitting(false);
    }
  };

  const material = plan?.material ?? "—";
  const complexity = time?.complexity_score ?? null;
  const setupCount = plan?.setups?.length ?? 0;

  return (
    <div className="flex items-center gap-4 px-4 py-2 w-full">
      {/* Summary pills */}
      <div className="flex items-center gap-3 flex-1 overflow-x-auto">
        <Pill
          icon={<Layers className="h-3 w-3" />}
          label="Strategy"
          value={selectedStrategy ?? "Default"}
        />
        <Pill
          icon={<Clock className="h-3 w-3" />}
          label="Time"
          value={time ? `${time.total_time?.toFixed(1)}m` : "—"}
        />
        <Pill
          icon={<DollarSign className="h-3 w-3" />}
          label="Cost"
          value={cost ? `$${cost.total_cost?.toFixed(2)}` : "—"}
        />
        <Pill
          icon={<FileText className="h-3 w-3" />}
          label="Material"
          value={material}
        />
        <Pill
          icon={<Layers className="h-3 w-3" />}
          label="Setups"
          value={String(setupCount)}
        />
        {complexity != null && (
          <Badge
            variant={complexity >= 7 ? "destructive" : "secondary"}
            className="text-[10px] h-5 shrink-0"
          >
            Complexity {complexity.toFixed(1)}
          </Badge>
        )}
      </div>

      {/* Submit button */}
      {submitted ? (
        <div className="flex items-center gap-1.5 text-emerald-500 shrink-0">
          <CheckCircle2 className="h-4 w-4" />
          <span className="text-xs font-medium">RFQ Submitted</span>
        </div>
      ) : (
        <Button
          size="sm"
          className="shrink-0 gap-1.5"
          disabled={isSubmitting || !modelId}
          onClick={handleSubmit}
        >
          {isSubmitting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
          Submit to Vendors
        </Button>
      )}
    </div>
  );
}

function Pill({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground shrink-0">
      {icon}
      <span className="text-muted-foreground/60">{label}:</span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}
