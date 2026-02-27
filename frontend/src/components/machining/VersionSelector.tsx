import { useEffect, useState, useCallback } from "react";
import { CheckCircle, History, Loader2 } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { listVersions } from "@/lib/planning-api";
import type { VersionSummary } from "@/types/machining";

// ─── Props ───────────────────────────────────────────────────────────────────

interface VersionSelectorProps {
  /** The model_id used to fetch version list. */
  modelId: string;
  /** Currently displayed version number. */
  currentVersion: number;
  /** Whether there are unsaved edits (blocks version switch). */
  dirty: boolean;
  /** Called when the user picks a different version. */
  onSelectVersion: (version: number) => void;
  /** Incremented externally to force a refresh of the version list. */
  refreshKey?: number;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs.toFixed(0)}s`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

export function VersionSelector({
  modelId,
  currentVersion,
  dirty,
  onSelectVersion,
  refreshKey = 0,
}: VersionSelectorProps) {
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [loading, setLoading] = useState(false);

  // Fetch version list on mount and whenever refreshKey changes
  const fetchVersions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listVersions(modelId);
      setVersions(data);
    } catch {
      // Silently fail — selector just won't show options
    } finally {
      setLoading(false);
    }
  }, [modelId]);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions, refreshKey]);

  if (loading && versions.length === 0) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="size-3.5 animate-spin" />
        Loading versions…
      </div>
    );
  }

  // Only one version — no need for a picker
  if (versions.length <= 1) return null;

  return (
    <div className="flex items-center gap-2">
      <History className="size-4 text-muted-foreground" />
      <Select
        value={String(currentVersion)}
        onValueChange={(val) => onSelectVersion(Number(val))}
        disabled={dirty}
      >
        <SelectTrigger className="h-8 w-52 text-xs">
          <SelectValue placeholder="Select version" />
        </SelectTrigger>
        <SelectContent>
          {versions.map((v) => (
            <SelectItem
              key={v.version}
              value={String(v.version)}
              className="text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono font-medium">v{v.version}</span>
                {v.approved && (
                  <CheckCircle className="size-3 text-emerald-600" />
                )}
                <span className="text-muted-foreground">
                  {v.operation_count} ops · {formatTime(v.estimated_time)}
                </span>
                <span className="text-muted-foreground">
                  {formatDate(v.created_at)}
                </span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {dirty && (
        <span className="text-[10px] text-amber-600">
          Save or discard changes first
        </span>
      )}
    </div>
  );
}
