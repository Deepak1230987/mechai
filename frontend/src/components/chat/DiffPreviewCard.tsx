/**
 * DiffPreviewCard — displays proposed plan changes with Confirm/Reject.
 */

import { Button } from "@/components/ui/button";
import { Check, X, ArrowRight } from "lucide-react";

interface DiffPreviewCardProps {
  before: string;
  after: string;
  description?: string;
  onConfirm: () => void;
  onReject: () => void;
  isProcessing?: boolean;
}

export function DiffPreviewCard({
  before,
  after,
  description,
  onConfirm,
  onReject,
  isProcessing,
}: DiffPreviewCardProps) {
  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 my-2">
      {description && (
        <p className="text-xs text-muted-foreground mb-2">{description}</p>
      )}

      <div className="flex items-center gap-2 text-[11px] font-mono">
        {/* Before */}
        <div className="flex-1 rounded bg-red-500/10 border border-red-500/20 px-2 py-1">
          <span className="text-[9px] text-red-400 font-sans uppercase tracking-wider">
            Before
          </span>
          <p className="text-foreground/70 mt-0.5 line-clamp-3 whitespace-pre-wrap">
            {before}
          </p>
        </div>

        <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />

        {/* After */}
        <div className="flex-1 rounded bg-emerald-500/10 border border-emerald-500/20 px-2 py-1">
          <span className="text-[9px] text-emerald-400 font-sans uppercase tracking-wider">
            After
          </span>
          <p className="text-foreground/70 mt-0.5 line-clamp-3 whitespace-pre-wrap">
            {after}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 mt-2">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-xs"
          onClick={onReject}
          disabled={isProcessing}
        >
          <X className="h-3 w-3 mr-1" />
          Reject
        </Button>
        <Button
          size="sm"
          className="h-7 text-xs"
          onClick={onConfirm}
          disabled={isProcessing}
        >
          <Check className="h-3 w-3 mr-1" />
          Confirm
        </Button>
      </div>
    </div>
  );
}
