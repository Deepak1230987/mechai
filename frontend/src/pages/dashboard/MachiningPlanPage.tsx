import { useEffect, useCallback, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ArrowLeft,
  Loader2,
  AlertCircle,
  Plus,
  Wrench,
  Download,
  FileText,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { PlanHeader } from "@/components/machining/PlanHeader";
import { OperationList } from "@/components/machining/OperationList";
import { ToolEditor } from "@/components/machining/ToolEditor";
import { SetupCard } from "@/components/machining/SetupCard";
import { CopilotChatPanel } from "@/components/machining/CopilotChatPanel";
import { VersionSelector } from "@/components/machining/VersionSelector";

import { usePlanEditor } from "@/hooks/usePlanEditor";
import { useAuth } from "@/hooks/useAuth";
import { chatRefinePlan, exportPlanPdf } from "@/lib/planning-api";
import type {
  Operation,
  Setup,
  MachineType,
  MachiningPlan,
} from "@/types/machining";

// ─── Constants ───────────────────────────────────────────────────────────────

const MATERIALS = [
  { value: "ALUMINUM_6061", label: "Aluminum 6061" },
  { value: "ALUMINUM_7075", label: "Aluminum 7075" },
  { value: "STEEL_1045", label: "Steel 1045" },
  { value: "STEEL_4140", label: "Steel 4140" },
  { value: "STAINLESS_304", label: "Stainless Steel 304" },
  { value: "STAINLESS_316", label: "Stainless Steel 316" },
  { value: "TITANIUM_6AL4V", label: "Titanium 6Al-4V" },
  { value: "BRASS_360", label: "Brass 360" },
  { value: "COPPER_110", label: "Copper 110" },
  { value: "DELRIN", label: "Delrin (POM)" },
  { value: "NYLON", label: "Nylon" },
  { value: "PEEK", label: "PEEK" },
] as const;

const MACHINE_TYPES: { value: MachineType; label: string }[] = [
  { value: "MILLING_3AXIS", label: "3-Axis Milling" },
  { value: "LATHE", label: "CNC Lathe" },
];

// ─── Page ────────────────────────────────────────────────────────────────────

export function MachiningPlanPage() {
  const { modelId } = useParams<{ modelId: string }>();
  const { user } = useAuth();

  // Generate-form local state
  const [material, setMaterial] = useState("ALUMINUM_6061");
  const [machineType, setMachineType] = useState<MachineType>("MILLING_3AXIS");

  const {
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
    applyProposedPlan,
  } = usePlanEditor();

  // Track version list refresh — incremented after save, approve, generate, chat
  const [versionRefreshKey, setVersionRefreshKey] = useState(0);

  // ── Fetch on mount ────────────────────────────────────────────────────
  useEffect(() => {
    if (modelId) fetchPlan(modelId);
  }, [modelId, fetchPlan]);

  // ── Bridge: OperationRow uses (id, patch) → hook uses (index, full) ──
  const handleUpdateOperation = useCallback(
    (id: string, patch: Partial<Operation>) => {
      if (!editablePlan) return;
      const idx = editablePlan.operations.findIndex((o) => o.id === id);
      if (idx === -1) return;
      const merged = { ...editablePlan.operations[idx], ...patch };
      updateOperation(idx, merged);
    },
    [editablePlan, updateOperation],
  );

  const handleDeleteOperation = useCallback(
    (id: string) => {
      if (!editablePlan) return;
      const idx = editablePlan.operations.findIndex((o) => o.id === id);
      if (idx !== -1) deleteOperation(idx);
    },
    [editablePlan, deleteOperation],
  );

  const handleAddOperation = useCallback(() => {
    const toolId = editablePlan?.tools[0]?.id ?? "tool_1";
    const op: Operation = {
      id: `op_${crypto.randomUUID().slice(0, 8)}`,
      feature_id: "",
      type: "FACE_MILLING",
      tool_id: toolId,
      parameters: {},
      estimated_time: 0,
    };
    addOperation(op);
  }, [editablePlan, addOperation]);

  // ── Bridge: SetupCard uses (id, patch) → hook uses (index, full) ─────
  const handleUpdateSetup = useCallback(
    (setupId: string, patch: Partial<Setup>) => {
      if (!editablePlan) return;
      const idx = editablePlan.setups.findIndex((s) => s.setup_id === setupId);
      if (idx === -1) return;
      const merged = { ...editablePlan.setups[idx], ...patch };
      updateSetup(idx, merged);
    },
    [editablePlan, updateSetup],
  );

  const handleDeleteSetup = useCallback(
    (setupId: string) => {
      if (!editablePlan) return;
      const idx = editablePlan.setups.findIndex((s) => s.setup_id === setupId);
      if (idx !== -1) deleteSetup(idx);
    },
    [editablePlan, deleteSetup],
  );

  const handleAddSetup = useCallback(() => {
    const setup: Setup = {
      setup_id: `setup_${crypto.randomUUID().slice(0, 8)}`,
      orientation: "TOP",
      operations: [],
    };
    addSetup(setup);
  }, [addSetup]);

  // ── Version switch handler ────────────────────────────────────────────
  const handleSelectVersion = useCallback(
    (versionNum: number) => {
      if (!modelId) return;
      loadVersion(modelId, versionNum);
    },
    [modelId, loadVersion],
  );

  // ── Copilot chat send handler ─────────────────────────────────────────
  const [exporting, setExporting] = useState(false);

  const handleCopilotSend = useCallback(
    async (message: string) => {
      const planId = editablePlan?.plan_id;
      if (!planId) throw new Error("No plan ID available.");
      const res = await chatRefinePlan(planId, { user_message: message });
      return {
        type: res.type,
        message: res.message,
        explanation: res.explanation,
        machining_plan: res.machining_plan as unknown as Record<
          string,
          unknown
        >,
        version: res.version,
      };
    },
    [editablePlan],
  );

  // ── Copilot plan update handler ───────────────────────────────────────
  const handleCopilotPlanUpdated = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (rawPlan: Record<string, unknown>, _version: number) => {
      // Copilot returned a new plan version — refresh from the typed object.
      const plan = rawPlan as unknown as MachiningPlan;
      // The hook needs to fully replace both original and editable to stay
      // in sync and clear dirty state (the backend already persisted it).
      fetchPlan(plan.model_id);
      setVersionRefreshKey((k) => k + 1);
    },
    [fetchPlan],
  );

  // ── Copilot plan propose handler ───────────────────────────────────────
  const handleCopilotPlanProposed = useCallback(
    (proposedPlan: Record<string, unknown>) => {
      if (!editablePlan) return;
      const plan = proposedPlan as unknown as MachiningPlan;
      applyProposedPlan(plan);
    },
    [editablePlan, applyProposedPlan]
  );

  // ── PDF download handler ──────────────────────────────────────────────
  const handleExportPdf = useCallback(async () => {
    const planId = editablePlan?.plan_id;
    if (!planId) return;
    setExporting(true);
    try {
      const blob = await exportPlanPdf(planId, {
        include_narrative: true,
      });
      // Trigger browser download
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `process_plan_v${editablePlan.version}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      // Error will surface via the api interceptor
    } finally {
      setExporting(false);
    }
  }, [editablePlan]);

  // ── Bridge: ToolEditor uses (toolId, patch) → hook uses (toolId, full)
  const handleUpdateTool = useCallback(
    (toolId: string, patch: Partial<import("@/types/machining").Tool>) => {
      if (!editablePlan) return;
      const tool = editablePlan.tools.find((t) => t.id === toolId);
      if (!tool) return;
      updateTool(toolId, { ...tool, ...patch });
    },
    [editablePlan, updateTool],
  );

  // ── Save / approve handlers ───────────────────────────────────────────
  const handleSave = useCallback(async () => {
    if (!user) return;
    try {
      await save(user.id);
      setVersionRefreshKey((k) => k + 1);
    } catch {
      // error is set in hook state
    }
  }, [save, user]);

  const handleApprove = useCallback(async () => {
    if (!user) return;
    try {
      await approve(user.id);
      setVersionRefreshKey((k) => k + 1);
    } catch {
      // error is set in hook state
    }
  }, [approve, user]);

  // ── Render: loading ───────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // ── Render: error (no plan) ───────────────────────────────────────────
  if (error && !editablePlan) {
    return (
      <div className="mx-auto max-w-xl py-20 text-center">
        <AlertCircle className="mx-auto mb-4 size-10 text-destructive" />
        <h2 className="mb-2 text-lg font-semibold">Error loading plan</h2>
        <p className="mb-6 text-sm text-muted-foreground">{error}</p>
        <Button asChild variant="outline">
          <Link to={`/models/${modelId}`}>
            <ArrowLeft className="mr-2 size-4" />
            Back to Model
          </Link>
        </Button>
      </div>
    );
  }

  // ── Render: no plan yet → generate form ──────────────────────────────
  if (noPlanYet && !editablePlan) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <Link
          to={`/models/${modelId}`}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Back to Model
        </Link>

        <Card className="mx-auto w-full max-w-lg">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Wrench className="size-5" />
              Generate Machining Plan
            </CardTitle>
            <CardDescription>
              No plan exists for this model yet. Choose material and machine
              type to generate a machining plan.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {/* Material */}
            <div className="flex flex-col gap-2">
              <Label htmlFor="material">Material</Label>
              <Select value={material} onValueChange={setMaterial}>
                <SelectTrigger id="material" className="w-full">
                  <SelectValue placeholder="Select material" />
                </SelectTrigger>
                <SelectContent>
                  {MATERIALS.map((m) => (
                    <SelectItem key={m.value} value={m.value}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Machine type */}
            <div className="flex flex-col gap-2">
              <Label htmlFor="machine-type">Machine Type</Label>
              <Select
                value={machineType}
                onValueChange={(v) => setMachineType(v as MachineType)}
              >
                <SelectTrigger id="machine-type" className="w-full">
                  <SelectValue placeholder="Select machine type" />
                </SelectTrigger>
                <SelectContent>
                  {MACHINE_TYPES.map((mt) => (
                    <SelectItem key={mt.value} value={mt.value}>
                      {mt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Error inline */}
            {error && <p className="text-sm text-destructive">{error}</p>}

            {/* Generate button */}
            <Button
              className="w-full"
              disabled={generating || !modelId}
              onClick={() => {
                if (!modelId) return;
                generateNewPlan({
                  model_id: modelId,
                  material,
                  machine_type: machineType,
                });
              }}
            >
              {generating ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" />
                  Generating…
                </>
              ) : (
                "Generate Machining Plan"
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!editablePlan) return null;

  const toolIds = editablePlan.tools.map((t) => t.id);

  // ── Render: plan editor (split layout) ────────────────────────────────
  return (
    <div className="relative min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/20 via-background to-background">
      <div className="relative z-10 flex flex-col gap-6 p-6">
        {/* Back link */}
        <Link
          to={`/models/${modelId}`}
          className="flex w-fit items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground hover:drop-shadow-md"
        >
          <ArrowLeft className="size-4" />
          Back to Model
        </Link>

      {/* Version selector + Header */}
      {modelId && (
        <VersionSelector
          modelId={modelId}
          currentVersion={editablePlan.version}
          dirty={dirty}
          onSelectVersion={handleSelectVersion}
          refreshKey={versionRefreshKey}
        />
      )}

      <PlanHeader
        plan={editablePlan}
        dirty={dirty}
        saving={saving}
        approving={approving}
        onSave={handleSave}
        onApprove={handleApprove}
        onDiscard={discard}
      />

      {/* Inline error banner */}
      {error && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Last diff summary */}
      {lastDiff && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Last Save Diff
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            {lastDiff.operations_added.length > 0 && (
              <span className="text-emerald-600">
                +{lastDiff.operations_added.length} ops added
              </span>
            )}
            {lastDiff.operations_removed.length > 0 && (
              <span className="text-destructive">
                -{lastDiff.operations_removed.length} ops removed
              </span>
            )}
            {lastDiff.operations_changed.length > 0 && (
              <span className="text-amber-600">
                ~{lastDiff.operations_changed.length} ops changed
              </span>
            )}
            {lastDiff.tools_changed.length > 0 && (
              <span className="text-blue-600">
                {lastDiff.tools_changed.length} tools changed
              </span>
            )}
            {lastDiff.order_changed && <span>Order changed</span>}
            {lastDiff.setups_changed && <span>Setups changed</span>}
            {lastDiff.time_delta !== 0 && (
              <span>
                Time {lastDiff.time_delta > 0 ? "+" : ""}
                {lastDiff.time_delta.toFixed(1)}s
              </span>
            )}
          </CardContent>
        </Card>
      )}

      <Separator />

      {/* ── Split layout: Left = editor, Right = copilot ──────────────── */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_380px]">
        {/* Left column: Tabs (Operations | Tools | Setups) */}
        <div className="min-w-0">
          <Tabs defaultValue="operations" className="w-full">
            <TabsList>
              <TabsTrigger value="operations">
                Operations ({editablePlan.operations.length})
              </TabsTrigger>
              <TabsTrigger value="tools">
                Tools ({editablePlan.tools.length})
              </TabsTrigger>
              <TabsTrigger value="setups">
                Setups ({editablePlan.setups.length})
              </TabsTrigger>
            </TabsList>

            {/* Operations tab */}
            <TabsContent value="operations" className="mt-4">
              <OperationList
                operations={editablePlan.operations}
                toolIds={toolIds}
                onUpdate={handleUpdateOperation}
                onDelete={handleDeleteOperation}
                onReorder={reorderOperations}
                onAdd={handleAddOperation}
              />
            </TabsContent>

            {/* Tools tab */}
            <TabsContent value="tools" className="mt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                {editablePlan.tools.map((tool) => (
                  <ToolEditor
                    key={tool.id}
                    tool={tool}
                    onUpdate={handleUpdateTool}
                  />
                ))}
              </div>
            </TabsContent>

            {/* Setups tab */}
            <TabsContent value="setups" className="mt-4">
              <div className="flex flex-col gap-4">
                <div className="flex justify-end">
                  <Button variant="outline" size="sm" onClick={handleAddSetup}>
                    <Plus className="mr-1 size-4" />
                    Add Setup
                  </Button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  {editablePlan.setups.map((setup) => (
                    <SetupCard
                      key={setup.setup_id}
                      setup={setup}
                      operations={editablePlan.operations}
                      onUpdate={handleUpdateSetup}
                      onDelete={handleDeleteSetup}
                    />
                  ))}
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right column: Copilot Chat */}
        <div className="h-150 lg:sticky lg:top-6">
          <CopilotChatPanel
            modelId={modelId || ""}
            version={editablePlan.version}
            dirty={dirty}
            onPlanUpdated={handleCopilotPlanUpdated}
            onPlanProposed={handleCopilotPlanProposed}
            sendMessage={handleCopilotSend}
          />
        </div>
      </div>

        {/* ── Bottom bar: PDF Export ─────────────────────────────────────── */}
        <Separator className="opacity-50" />
        <div className="flex items-center justify-between rounded-xl border border-white/5 bg-background/40 p-4 shadow-sm backdrop-blur-md">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <div className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-primary">
              <FileText className="size-4" />
            </div>
            <span>Download the full process planning sheet as PDF</span>
          </div>
          <Button
            variant="outline"
            className="transition-all hover:-translate-y-0.5 hover:shadow-md"
            onClick={handleExportPdf}
            disabled={exporting || dirty}
          >
            {exporting ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Download className="mr-2 size-4" />
            )}
            {exporting ? "Generating…" : "Download Process Sheet"}
          </Button>
        </div>
      </div>
    </div>
  );
}
