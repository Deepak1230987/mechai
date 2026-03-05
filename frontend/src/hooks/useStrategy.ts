/**
 * useStrategy — manage strategy selection and live cost/time recalculation.
 */

import { useCallback } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { getCostBreakdown, getTimeBreakdown } from "@/lib/intelligence-api";

export function useStrategy() {
  const {
    modelId,
    selectedStrategy,
    strategies,
    setSelectedStrategy,
    setCost,
    setTime,
    setProcessingStage,
  } = useWorkspaceStore();

  const selectStrategy = useCallback(
    async (strategyName: string) => {
      setSelectedStrategy(strategyName);

      if (!modelId) return;
      setProcessingStage("optimizing");

      try {
        const [costRes, timeRes] = await Promise.all([
          getCostBreakdown(modelId, undefined, strategyName),
          getTimeBreakdown(modelId, undefined, strategyName),
        ]);
        setCost(costRes.data);
        setTime(timeRes.data);
      } catch {
        // silently fail — old data stays
      } finally {
        setProcessingStage("idle");
      }
    },
    [modelId, setCost, setTime, setSelectedStrategy, setProcessingStage],
  );

  return { selectedStrategy, strategies, selectStrategy };
}
