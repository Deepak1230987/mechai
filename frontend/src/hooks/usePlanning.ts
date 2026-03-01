/**
 * usePlanning — loads plan + intelligence data into the workspace store.
 * Auto-generates a machining plan when none exists for a READY model.
 */

import { useCallback, useEffect, useRef } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import {
    getLatestPlan,
    generatePlan,
    listVersions as apiListVersions,
} from "@/lib/planning-api";
import {
    getCostBreakdown,
    getTimeBreakdown,
    getSpatialMap,
} from "@/lib/intelligence-api";
import type { VersionInfo } from "@/types/intelligence";

export function usePlanning(modelId: string | undefined) {
    const {
        setPlan,
        setCost,
        setTime,
        setSpatialMap,
        setVersionHistory,
        setStrategies,
        setRisks,
        setProcessingStage,
        setError,
        plan,
    } = useWorkspaceStore();

    const loadedRef = useRef(false);

    // ── Helper: extract plan metadata into store ─────────────────────────
    const hydrateFromPlan = useCallback(
        (planData: Record<string, unknown>) => {
            if (Array.isArray(planData.strategies)) {
                setStrategies(
                    planData.strategies.map((s: Record<string, unknown>) => ({
                        name: String(s.name ?? ""),
                        description: String(s.description ?? ""),
                        estimated_time: Number(s.estimated_time ?? 0),
                    })),
                );
            }
            if (Array.isArray(planData.risks)) {
                setRisks(
                    planData.risks.map((r: Record<string, unknown>) => ({
                        type: String(r.type ?? ""),
                        severity: String(r.severity ?? "MEDIUM") as
                            | "LOW"
                            | "MEDIUM"
                            | "HIGH",
                        feature_id: String(r.feature_id ?? ""),
                        description: String(r.description ?? ""),
                    })),
                );
            }
        },
        [setStrategies, setRisks],
    );

    // ── Helper: fetch intelligence data in parallel ──────────────────────
    const loadIntelligence = useCallback(
        async (id: string) => {
            const [costRes, timeRes, spatialRes, versionsRes] =
                await Promise.allSettled([
                    getCostBreakdown(id),
                    getTimeBreakdown(id),
                    getSpatialMap(id),
                    apiListVersions(id),
                ]);

            if (costRes.status === "fulfilled") setCost(costRes.value.data);
            if (timeRes.status === "fulfilled") setTime(timeRes.value.data);
            if (spatialRes.status === "fulfilled")
                setSpatialMap(spatialRes.value.data);
            if (versionsRes.status === "fulfilled") {
                setVersionHistory(versionsRes.value as VersionInfo[]);
            }
        },
        [setCost, setTime, setSpatialMap, setVersionHistory],
    );

    // ── Main loader ──────────────────────────────────────────────────────
    const loadPlan = useCallback(async () => {
        if (!modelId) return;
        setProcessingStage("generating_plan");
        setError(null);

        try {
            let planData = await getLatestPlan(modelId);

            // ── Auto-generate if no plan exists ──────────────────────────
            if (!planData) {
                setProcessingStage("analyzing_geometry");

                try {
                    planData = await generatePlan({
                        model_id: modelId,
                        material: "ALUMINUM_6061",
                        machine_type: "MILLING_3AXIS",
                    });
                } catch (genErr) {
                    setError(
                        genErr instanceof Error
                            ? genErr.message
                            : "Failed to auto-generate machining plan",
                    );
                    setProcessingStage("idle");
                    return;
                }
            }

            setPlan(planData);
            hydrateFromPlan(planData as unknown as Record<string, unknown>);

            // Load intelligence in parallel
            setProcessingStage("optimizing");
            await loadIntelligence(modelId);

            setProcessingStage("idle");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load plan");
            setProcessingStage("idle");
        }
    }, [
        modelId,
        setPlan,
        hydrateFromPlan,
        loadIntelligence,
        setProcessingStage,
        setError,
    ]);

    // Load on mount
    useEffect(() => {
        if (modelId && !loadedRef.current) {
            loadedRef.current = true;
            loadPlan();
        }
    }, [modelId, loadPlan]);

    // Reload function for external use
    const reload = useCallback(() => {
        loadedRef.current = false;
        loadPlan();
    }, [loadPlan]);

    return { plan, reload };
}
