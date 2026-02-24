import { Badge } from "@/components/ui/badge";
import type { ModelStatus, RfqStatus } from "@/types";
import { cn } from "@/lib/utils";

type StatusType = ModelStatus | RfqStatus;

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  UPLOADED: {
    label: "Uploaded",
    className: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
  },
  PROCESSING: {
    label: "Processing",
    className:
      "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300",
  },
  READY: {
    label: "Ready",
    className:
      "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
  },
  PENDING: {
    label: "Pending",
    className:
      "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300",
  },
  QUOTED: {
    label: "Quoted",
    className:
      "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300",
  },
  ACCEPTED: {
    label: "Accepted",
    className:
      "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
  },
  REJECTED: {
    label: "Rejected",
    className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
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
      className={cn("font-medium border-0", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}
