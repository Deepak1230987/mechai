/**
 * useVersioning — manage version history, rollback, and version switching.
 */

import { useCallback, useState } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import {
  rollbackPlan,
  listVersions,
  getCostBreakdown,
  getTimeBreakdown,
  getSpatialMap,
} from "@/lib/intelligence-api";
import { getLatestPlan } from "@/lib/planning-api";
import type { VersionInfo } from "@/types/intelligence";

export function useVersioning() {
  const {
    modelId,
    versionHistory,
    setVersionHistory,
    setPlan,
    setCost,
    setTime,
    setSpatialMap,
    setProcessingStage,
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
      setProcessingStage("optimizing");
      try {
        await rollbackPlan(modelId, targetVersion);

        // Full reload: plan, intelligence data, and versions
        const [planData, costRes, timeRes, spatialRes, versions] =
          await Promise.allSettled([
            getLatestPlan(modelId),
            getCostBreakdown(modelId),
            getTimeBreakdown(modelId),
            getSpatialMap(modelId),
            listVersions(modelId),
          ]);

        if (planData.status === "fulfilled" && planData.value) {
          setPlan(planData.value);
        }
        if (costRes.status === "fulfilled") setCost(costRes.value.data);
        if (timeRes.status === "fulfilled") setTime(timeRes.value.data);
        if (spatialRes.status === "fulfilled") setSpatialMap(spatialRes.value.data);
        if (versions.status === "fulfilled") {
          setVersionHistory(versions.value as VersionInfo[]);
        }

        return true;
      } catch {
        return false;
      } finally {
        setIsRollingBack(false);
        setProcessingStage("idle");
      }
    },
    [modelId, setPlan, setCost, setTime, setSpatialMap, setVersionHistory, setProcessingStage],
  );

  return {
    versionHistory,
    currentVersion: plan?.version ?? 0,
    isRollingBack,
    refreshVersions,
    rollback,
  };
}
