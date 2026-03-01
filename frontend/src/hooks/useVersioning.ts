/**
 * useVersioning — manage version history, rollback, and version switching.
 */

import { useCallback, useState } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { rollbackPlan, listVersions } from "@/lib/intelligence-api";
import type { VersionInfo } from "@/types/intelligence";

export function useVersioning() {
  const {
    modelId,
    versionHistory,
    setVersionHistory,
    plan,
  } = useWorkspaceStore();
  const [isRollingBack, setIsRollingBack] = useState(false);

  const refreshVersions = useCallback(async () => {
    if (!modelId) return;
    try {
      const versions = await listVersions(modelId);
      setVersionHistory(versions as VersionInfo[]);
    } catch {
      // silently fail
    }
  }, [modelId, setVersionHistory]);

  const rollback = useCallback(
    async (targetVersion: number): Promise<boolean> => {
      if (!modelId) return false;
      setIsRollingBack(true);
      try {
        await rollbackPlan(modelId, targetVersion);
        await refreshVersions();
        return true;
      } catch {
        return false;
      } finally {
        setIsRollingBack(false);
      }
    },
    [modelId, refreshVersions],
  );

  return {
    versionHistory,
    currentVersion: plan?.version ?? 0,
    isRollingBack,
    refreshVersions,
    rollback,
  };
}
