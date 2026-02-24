import { Badge } from "@/components/ui/badge";
import type { ModelStatus, RfqStatus } from "@/types";
import { cn } from "@/lib/utils";

type StatusType = ModelStatus | RfqStatus;

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  UPLOADED: {
    label: "Uploaded",
    className: "bg-blue-500/10 text-blue-400 border border-blue-500/20",
  },
  PROCESSING: {
    label: "Processing",
    className: "bg-amber-500/10 text-amber-400 border border-amber-500/20",
  },
  READY: {
    label: "Ready",
    className:
      "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  },
  PENDING: {
    label: "Pending",
    className: "bg-orange-500/10 text-orange-400 border border-orange-500/20",
  },
  QUOTED: {
    label: "Quoted",
    className: "bg-violet-500/10 text-violet-400 border border-violet-500/20",
  },
  ACCEPTED: {
    label: "Accepted",
    className:
      "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20",
  },
  REJECTED: {
    label: "Rejected",
    className: "bg-red-500/10 text-red-400 border border-red-500/20",
  },
  FAILED: {
    label: "Failed",
    className: "bg-red-500/10 text-red-400 border border-red-500/20",
  },
};

interface StatusBadgeProps {
  status: StatusType;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status];
  return (
    <Badge
      variant="secondary"
      className={cn(
        "font-medium border-0 rounded px-2 py-0.5 text-[11px]",
        config.className,
        className,
      )}
    >
      {config.label}
    </Badge>
  );
}
