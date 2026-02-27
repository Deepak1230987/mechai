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
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <h1 className="bg-gradient-to-br from-foreground to-foreground/70 bg-clip-text text-2xl font-bold tracking-tight text-transparent">
            Machining Plan
          </h1>
          <Badge variant="outline" className="font-mono text-xs shadow-sm bg-background/50">
            v{plan.version}
          </Badge>
          {plan.approved ? (
            <Badge className="bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 shadow-sm border-emerald-500/20">
              <CheckCircle className="mr-1.5 size-3.5" />
              Approved
            </Badge>
          ) : (
            <Badge variant="secondary" className="shadow-sm">Not Approved</Badge>
          )}
          {dirty && (
            <Badge variant="outline" className="animate-[pulse_2s_ease-in-out_infinite] border-amber-500/50 bg-amber-500/10 text-amber-500 shadow-sm">
              <AlertTriangle className="mr-1.5 size-3.5" />
              Unsaved Changes
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-4 text-sm font-medium text-muted-foreground/80">
          <span className="flex items-center gap-1.5">
            <Clock className="size-4 text-primary/70" />
            {formatTime(plan.estimated_time)}
          </span>
          <span className="flex items-center gap-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary/50" />
            {plan.material}
          </span>
          <span className="flex items-center gap-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary/50" />
            {plan.machine_type.replace("_", " ")}
          </span>
          <span className="flex items-center gap-1.5">
             <div className="h-1.5 w-1.5 rounded-full bg-primary/50" />
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
          className="shadow-md transition-all hover:-translate-y-0.5"
        >
          {saving ? (
            <Loader2 className="mr-1.5 size-4 animate-spin" />
          ) : (
            <Save className="mr-1.5 size-4" />
          )}
          {saving ? "Saving…" : "Save Changes"}
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
