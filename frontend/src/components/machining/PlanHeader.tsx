import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import type { MachiningPlan } from "@/types/machining";
import {
  CheckCircle,
  Clock,
  Loader2,
  Save,
  ShieldCheck,
  Undo2,
  AlertTriangle,
} from "lucide-react";

interface PlanHeaderProps {
  plan: MachiningPlan;
  dirty: boolean;
  saving: boolean;
  approving: boolean;
  onSave: () => void;
  onApprove: () => void;
  onDiscard: () => void;
}

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs.toFixed(0)}s`;
}

export function PlanHeader({
  plan,
  dirty,
  saving,
  approving,
  onSave,
  onApprove,
  onDiscard,
}: PlanHeaderProps) {
  const canApprove = !dirty && !plan.approved;

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      {/* Left: title + metadata */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">
            Machining Plan
          </h1>
          <Badge variant="outline" className="font-mono text-xs">
            v{plan.version}
          </Badge>
          {plan.approved ? (
            <Badge className="bg-emerald-600 text-white">
              <CheckCircle className="mr-1 size-3" />
              Approved
            </Badge>
          ) : (
            <Badge variant="secondary">Not Approved</Badge>
          )}
          {dirty && (
            <Badge variant="destructive" className="animate-pulse">
              <AlertTriangle className="mr-1 size-3" />
              Unsaved Changes
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1">
            <Clock className="size-3.5" />
            {formatTime(plan.estimated_time)}
          </span>
          <span>{plan.material}</span>
          <span>{plan.machine_type.replace("_", " ")}</span>
          <span>
            {plan.operations.length} ops · {plan.tools.length} tools ·{" "}
            {plan.setups.length} setups
          </span>
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-2">
        {dirty && (
          <Button variant="ghost" size="sm" onClick={onDiscard}>
            <Undo2 className="mr-1 size-4" />
            Discard
          </Button>
        )}

        <Button
          variant="default"
          size="sm"
          onClick={onSave}
          disabled={!dirty || saving}
        >
          {saving ? (
            <Loader2 className="mr-1 size-4 animate-spin" />
          ) : (
            <Save className="mr-1 size-4" />
          )}
          {saving ? "Saving…" : "Save"}
        </Button>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              disabled={!canApprove || approving}
              className={canApprove ? "border-emerald-600 text-emerald-600 hover:bg-emerald-50" : ""}
            >
              {approving ? (
                <Loader2 className="mr-1 size-4 animate-spin" />
              ) : (
                <ShieldCheck className="mr-1 size-4" />
              )}
              {approving ? "Approving…" : "Approve"}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Approve Machining Plan?</AlertDialogTitle>
              <AlertDialogDescription>
                This marks plan v{plan.version} as approved for RFQ. The plan
                will be re-validated before approval. Any future edits will
                reset approval status.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={onApprove}>
                Yes, Approve
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
