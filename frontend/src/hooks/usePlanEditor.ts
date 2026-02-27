import { useState, useCallback, useRef, useEffect } from "react";
import { getLatestPlan, getVersion, updatePlan, approvePlan, generatePlan } from "@/lib/planning-api";
import type { GeneratePlanRequest } from "@/lib/planning-api";
import type {
    MachiningPlan,
    Operation,
    Setup,
    Tool,
    PlanDiff,
} from "@/types/machining";

// ─── Hook State ──────────────────────────────────────────────────────────────

interface PlanEditorState {
    originalPlan: MachiningPlan | null;
    editablePlan: MachiningPlan | null;
    dirty: boolean;
    loading: boolean;
    saving: boolean;
    approving: boolean;
    generating: boolean;
    noPlanYet: boolean;
    error: string | null;
    lastDiff: PlanDiff | null;
}

// ─── Return Type ─────────────────────────────────────────────────────────────

export interface PlanEditorActions {
    /** Fetch the latest plan for a model from the server. */
    fetchPlan: (modelId: string) => Promise<void>;

    /** Generate a brand-new plan for a model (first time). */
    generateNewPlan: (req: GeneratePlanRequest) => Promise<void>;

    /** Replace an operation at a specific index. */
    updateOperation: (index: number, updated: Operation) => void;

    /** Reorder operations by moving from one index to another. */
    reorderOperations: (fromIndex: number, toIndex: number) => void;

    /** Append a new operation. */
    addOperation: (operation: Operation) => void;

    /** Remove an operation by index. */
    deleteOperation: (index: number) => void;

    /** Replace a tool by ID. */
    updateTool: (toolId: string, updated: Tool) => void;

    /** Add a new setup. */
    addSetup: (setup: Setup) => void;

    /** Update a setup by index. */
    updateSetup: (index: number, updated: Setup) => void;

    /** Delete a setup by index. */
    deleteSetup: (index: number) => void;

    /** Save edits to backend (creates new version). */
    save: (userId: string) => Promise<void>;

    /** Approve the current saved plan. */
    approve: (userId: string) => Promise<void>;

    /** Reset editable plan to original (discard changes). */
    discard: () => void;

    /** Load a specific version for the current model. */
    loadVersion: (modelId: string, versionNum: number) => Promise<void>;
}

export type UsePlanEditorReturn = PlanEditorState & PlanEditorActions;

// ─── Hook ────────────────────────────────────────────────────────────────────

export function usePlanEditor(): UsePlanEditorReturn {
    const [originalPlan, setOriginalPlan] = useState<MachiningPlan | null>(null);
    const [editablePlan, setEditablePlan] = useState<MachiningPlan | null>(null);
    const [dirty, setDirty] = useState(false);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [approving, setApproving] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [noPlanYet, setNoPlanYet] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lastDiff, setLastDiff] = useState<PlanDiff | null>(null);

    // Keep a stable ref to the current plan_id for save/approve calls.
    // plan_id comes from the server — we need it but the backend returns
    // the plan_id embedded differently. Since the GET /latest doesn't
    // expose the DB row `id`, we'll store it when we receive a response
    // from the update endpoint.
    const planIdRef = useRef<string | null>(null);

    // ── Fetch ────────────────────────────────────────────────────────────
    const fetchPlan = useCallback(async (modelId: string) => {
        setLoading(true);
        setError(null);
        setNoPlanYet(false);
        try {
            const plan = await getLatestPlan(modelId);
            if (plan === null) {
                // 404 — no plan generated yet
                setNoPlanYet(true);
                return;
            }
            setOriginalPlan(structuredClone(plan));
            setEditablePlan(structuredClone(plan));
            setDirty(false);
            setLastDiff(null);
            // Store the DB row ID so we can call /update and /approve.
            planIdRef.current = plan.plan_id;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load plan");
        } finally {
            setLoading(false);
        }
    }, []);

    // ── Generate ─────────────────────────────────────────────────────────
    const generateNewPlan = useCallback(async (req: GeneratePlanRequest) => {
        setGenerating(true);
        setError(null);
        try {
            const plan = await generatePlan(req);
            setOriginalPlan(structuredClone(plan));
            setEditablePlan(structuredClone(plan));
            setDirty(false);
            setNoPlanYet(false);
            setLastDiff(null);
            planIdRef.current = plan.plan_id;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Plan generation failed");
        } finally {
            setGenerating(false);
        }
    }, []);

    // ── Edit helpers (all operate on editablePlan, set dirty) ────────────

    const markDirty = useCallback(() => setDirty(true), []);

    const updateOperation = useCallback(
        (index: number, updated: Operation) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const ops = [...prev.operations];
                ops[index] = updated;
                return { ...prev, operations: ops };
            });
            markDirty();
        },
        [markDirty],
    );

    const reorderOperations = useCallback(
        (fromIndex: number, toIndex: number) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const ops = [...prev.operations];
                const [moved] = ops.splice(fromIndex, 1);
                ops.splice(toIndex, 0, moved);
                return { ...prev, operations: ops };
            });
            markDirty();
        },
        [markDirty],
    );

    const addOperation = useCallback(
        (operation: Operation) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                return { ...prev, operations: [...prev.operations, operation] };
            });
            markDirty();
        },
        [markDirty],
    );

    const deleteOperation = useCallback(
        (index: number) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const ops = prev.operations.filter((_, i) => i !== index);
                return { ...prev, operations: ops };
            });
            markDirty();
        },
        [markDirty],
    );

    const updateTool = useCallback(
        (toolId: string, updated: Tool) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const tools = prev.tools.map((t) => (t.id === toolId ? updated : t));
                return { ...prev, tools };
            });
            markDirty();
        },
        [markDirty],
    );

    const addSetup = useCallback(
        (setup: Setup) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                return { ...prev, setups: [...prev.setups, setup] };
            });
            markDirty();
        },
        [markDirty],
    );

    const updateSetup = useCallback(
        (index: number, updated: Setup) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const setups = [...prev.setups];
                setups[index] = updated;
                return { ...prev, setups };
            });
            markDirty();
        },
        [markDirty],
    );

    const deleteSetup = useCallback(
        (index: number) => {
            setEditablePlan((prev) => {
                if (!prev) return prev;
                const setups = prev.setups.filter((_, i) => i !== index);
                return { ...prev, setups };
            });
            markDirty();
        },
        [markDirty],
    );

    // ── Save ─────────────────────────────────────────────────────────────
    const save = useCallback(
        async (userId: string) => {
            if (!editablePlan || !originalPlan) return;
            setSaving(true);
            setError(null);

            try {
                // We need the plan_id (DB row ID). If we have it from a previous
                // save, use it. Otherwise derive from model_id — the backend
                // /update endpoint needs the original plan's DB id.
                const id = planIdRef.current;
                if (!id) {
                    throw new Error(
                        "Cannot save: no plan ID available. " +
                        "The plan may not have been generated yet.",
                    );
                }

                const res = await updatePlan(id, {
                    edited_plan: {
                        setups: editablePlan.setups,
                        operations: editablePlan.operations,
                        tools: editablePlan.tools,
                        estimated_time: editablePlan.estimated_time,
                    },
                    edited_by: userId,
                });

                // Update both copies with the new version from server
                setOriginalPlan(structuredClone(res.plan));
                setEditablePlan(structuredClone(res.plan));
                setDirty(false);
                setLastDiff(res.diff);
                // The new plan has its own ID — store it for future saves
                planIdRef.current = res.plan.plan_id;
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to save plan");
                throw err;
            } finally {
                setSaving(false);
            }
        },
        [editablePlan, originalPlan],
    );

    // ── Approve ──────────────────────────────────────────────────────────
    const approve = useCallback(
        async (userId: string) => {
            if (!originalPlan || dirty) return;
            setApproving(true);
            setError(null);

            try {
                const id = planIdRef.current;
                if (!id) {
                    throw new Error("Cannot approve: no plan ID available.");
                }

                const approved = await approvePlan(id, { approved_by: userId });

                setOriginalPlan(structuredClone(approved));
                setEditablePlan(structuredClone(approved));
            } catch (err) {
                setError(
                    err instanceof Error ? err.message : "Failed to approve plan",
                );
                throw err;
            } finally {
                setApproving(false);
            }
        },
        [originalPlan, dirty],
    );

    // ── Discard ──────────────────────────────────────────────────────────
    const discard = useCallback(() => {
        if (originalPlan) {
            setEditablePlan(structuredClone(originalPlan));
            setDirty(false);
        }
    }, [originalPlan]);

    // ── Load specific version ────────────────────────────────────────────
    const loadVersion = useCallback(async (modelId: string, versionNum: number) => {
        setLoading(true);
        setError(null);
        try {
            const plan = await getVersion(modelId, versionNum);
            setOriginalPlan(structuredClone(plan));
            setEditablePlan(structuredClone(plan));
            setDirty(false);
            setLastDiff(null);
            planIdRef.current = plan.plan_id;
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load version");
        } finally {
            setLoading(false);
        }
    }, []);

    // ── Warn on navigation ──────────────────────────────────────────────
    useEffect(() => {
        if (!dirty) return;
        const handler = (e: BeforeUnloadEvent) => {
            e.preventDefault();
        };
        window.addEventListener("beforeunload", handler);
        return () => window.removeEventListener("beforeunload", handler);
    }, [dirty]);

    return {
        originalPlan,
        editablePlan,
        dirty,
        loading,
        saving,
        approving,
        generating,
        noPlanYet,
        error,
        lastDiff,
        fetchPlan,
        generateNewPlan,
        updateOperation,
        reorderOperations,
        addOperation,
        deleteOperation,
        updateTool,
        addSetup,
        updateSetup,
        deleteSetup,
        save,
        approve,
        discard,
        loadVersion,
    };
}
