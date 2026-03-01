/**
 * ModelWorkspace — the main workspace page assembling all panels.
 * Route: /models/:modelId/workspace
 */

import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { usePlanning } from "@/hooks/usePlanning";
import { useModelStatus } from "@/hooks/useModelStatus";
import { downloadIndustrialPDF } from "@/lib/intelligence-api";
import { WorkspaceLayout } from "@/components/layout/WorkspaceLayout";
import { WorkspaceSidebar } from "@/components/layout/Sidebar";
import { ThreeDViewer } from "@/components/viewer/ThreeDViewer";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { OperationTimeline } from "@/components/planning/OperationTimeline";
import { StrategySelector } from "@/components/planning/StrategySelector";
import { CostSummaryPanel } from "@/components/planning/CostSummaryPanel";
import { RiskPanel } from "@/components/planning/RiskPanel";
import { VersionHistoryPanel } from "@/components/planning/VersionHistoryPanel";
import { RFQSubmitPanel } from "@/components/rfq/RFQSubmitPanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2 } from "lucide-react";

export function ModelWorkspacePage() {
  const { modelId } = useParams<{ modelId: string }>();
  const navigate = useNavigate();
  const [isExporting, setIsExporting] = useState(false);

  const setModelId = useWorkspaceStore((s) => s.setModelId);
  const setModelName = useWorkspaceStore((s) => s.setModelName);
  const setGltfUrl = useWorkspaceStore((s) => s.setGltfUrl);
  const reset = useWorkspaceStore((s) => s.reset);
  const plan = useWorkspaceStore((s) => s.plan);

  // Load model details
  const { model, loading: modelLoading } = useModelStatus(modelId ?? undefined);

  // Sync model info to store
  useEffect(() => {
    if (!modelId) return;
    setModelId(modelId);
    return () => {
      reset();
    };
  }, [modelId, setModelId, reset]);

  useEffect(() => {
    if (model) {
      setModelName(model.original_filename ?? model.name ?? "Untitled");
      if (model.gltf_url) {
        setGltfUrl(model.gltf_url);
      }
    }
  }, [model, setModelName, setGltfUrl]);

  // Load planning data once model is ready
  usePlanning(modelId ?? undefined);

  // Export PDF handler
  const handleExportPDF = useCallback(async () => {
    if (!modelId) return;
    setIsExporting(true);
    try {
      const blob = await downloadIndustrialPDF(modelId, {
        include_cost: true,
        include_time: true,
        include_risk: true,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `manufacturing-report-${modelId.slice(0, 8)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Could add toast notification here
    } finally {
      setIsExporting(false);
    }
  }, [modelId]);

  // Redirect if no modelId
  useEffect(() => {
    if (!modelId) navigate("/models", { replace: true });
  }, [modelId, navigate]);

  // Processing stage labels for user feedback
  const processingStage = useWorkspaceStore((s) => s.processingStage);
  const error = useWorkspaceStore((s) => s.error);

  const stageLabel: Record<string, string> = {
    analyzing_geometry: "Analyzing geometry & auto-generating machining plan…",
    generating_plan: "Loading machining plan…",
    optimizing: "Loading cost, time & spatial intelligence…",
  };

  // Loading state — show stage progress
  if ((modelLoading || processingStage !== "idle") && !plan) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-10 w-10 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">
            {stageLabel[processingStage] ?? "Loading workspace…"}
          </p>
          {error && (
            <div className="max-w-md rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-center">
              <p className="text-sm text-destructive font-medium">{error}</p>
              <button
                className="mt-2 text-xs text-primary underline hover:no-underline"
                onClick={() => window.location.reload()}
              >
                Retry
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <WorkspaceLayout
      sidebar={
        <WorkspaceSidebar
          onExportPDF={handleExportPDF}
          isExporting={isExporting}
        />
      }
      viewer={<ThreeDViewer />}
      chat={<ChatPanel />}
      timeline={
        <div className="h-64 lg:h-72 overflow-hidden">
          <OperationTimeline />
        </div>
      }
      strategyCost={
        <ScrollArea className="h-64 lg:h-72">
          <Tabs defaultValue="cost" className="w-full">
            <TabsList className="w-full grid grid-cols-4 h-8">
              <TabsTrigger value="cost" className="text-[10px]">
                Cost
              </TabsTrigger>
              <TabsTrigger value="strategy" className="text-[10px]">
                Strategy
              </TabsTrigger>
              <TabsTrigger value="risks" className="text-[10px]">
                Risks
              </TabsTrigger>
              <TabsTrigger value="versions" className="text-[10px]">
                Versions
              </TabsTrigger>
            </TabsList>
            <TabsContent value="cost">
              <CostSummaryPanel />
            </TabsContent>
            <TabsContent value="strategy">
              <StrategySelector />
            </TabsContent>
            <TabsContent value="risks" className="h-48">
              <RiskPanel />
            </TabsContent>
            <TabsContent value="versions" className="h-48">
              <VersionHistoryPanel />
            </TabsContent>
          </Tabs>
        </ScrollArea>
      }
      bottomBar={
        <div className="border-t border-border bg-muted/10">
          <RFQSubmitPanel />
        </div>
      }
    />
  );
}
