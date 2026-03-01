import { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { GeometrySummaryCard } from "@/components/shared/GeometrySummaryCard";
import { FeaturePanel } from "@/components/shared/FeaturePanel";
import {
  STLWarningBanner,
  MeshModelInfoCard,
} from "@/components/shared/STLWarningBanner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ModelViewer } from "@/components/viewer/ModelViewer";
import { getModel, getViewerUrl } from "@/lib/models-api";
import type { Model } from "@/types";
import {
  ArrowLeft,
  Calendar,
  Eye,
  Hash,
  Layers,
  Loader2,
  AlertCircle,
  FileType,
  RefreshCw,
  Cog,
} from "lucide-react";

const POLL_INTERVAL_MS = 5_000;

export function ModelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [model, setModel] = useState<Model | null>(null);
  const [gltfUrl, setGltfUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Fetch model detail ──────────────────────────────────────────────
  useEffect(() => {
    if (!id) return;

    let cancelled = false;

    async function fetchModel() {
      try {
        const data = await getModel(id!);
        if (cancelled) return;
        setModel(data);
        setError("");

        // If READY, fetch the viewer URL
        if (data.status === "READY") {
          try {
            const viewer = await getViewerUrl(id!);
            if (!cancelled) setGltfUrl(viewer.gltf_url);
          } catch {
            // Viewer URL may fail — model is still shown
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load model");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    fetchModel();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // ── Polling for PROCESSING status ───────────────────────────────────
  useEffect(() => {
    if (!id || !model) return;

    // Only poll if status is PROCESSING or UPLOADED
    if (model.status !== "PROCESSING" && model.status !== "UPLOADED") {
      return;
    }

    pollRef.current = setInterval(async () => {
      try {
        const data = await getModel(id);
        setModel(data);

        // Stop polling once status changes to READY or FAILED
        if (data.status === "READY" || data.status === "FAILED") {
          if (pollRef.current) clearInterval(pollRef.current);

          // Fetch viewer URL if ready
          if (data.status === "READY") {
            try {
              const viewer = await getViewerUrl(id);
              setGltfUrl(viewer.gltf_url);
            } catch {
              // silently fail
            }
          }
        }
      } catch {
        // Keep polling on transient errors
      }
    }, POLL_INTERVAL_MS);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id, model?.status]);

  // ── Loading state ───────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">
          Loading model...
        </span>
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────
  if (error || !model) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <AlertCircle className="h-8 w-8 text-destructive mb-2" />
        <h2 className="text-xl font-semibold mb-2">
          {error || "Model not found"}
        </h2>
        <p className="text-muted-foreground mb-4">
          The model you're looking for doesn't exist or couldn't be loaded.
        </p>
        <Button asChild variant="outline">
          <Link to="/models">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Models
          </Link>
        </Button>
      </div>
    );
  }

  const isProcessing =
    model.status === "PROCESSING" || model.status === "UPLOADED";

  // ── STL awareness ─────────────────────────────────────────────────
  const isSTL = model.file_format?.toUpperCase() === "STL";

  return (
    <>
      <PageHeader title={model.name} description={`Model ID: ${model.id}`}>
        <Button asChild variant="outline">
          <Link to="/models">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Models
          </Link>
        </Button>
      </PageHeader>

      {/* STL banners — shown when model is READY and is STL */}
      {model.status === "READY" && isSTL && (
        <div className="space-y-3 mb-6">
          <STLWarningBanner />
          <MeshModelInfoCard />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Model info + viewer */}
        <Card className="lg:col-span-2 border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base font-semibold">
              Model Information
            </CardTitle>
            <CardDescription>
              Details and metadata for this CAD model.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex items-center gap-3">
                <Hash className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Version</p>
                  <p className="font-medium">v{model.version}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Layers className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <StatusBadge status={model.status} />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Visibility</p>
                  <Badge variant="outline" className="capitalize">
                    {model.visibility.toLowerCase()}
                  </Badge>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium">
                    {new Date(model.created_at).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <FileType className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Format</p>
                  <Badge variant="secondary">{model.file_format}</Badge>
                </div>
              </div>
            </div>

            <Separator />

            {/* 3D Viewer or status placeholder */}
            <div>
              <p className="text-sm text-muted-foreground mb-2">3D Viewer</p>

              {model.status === "READY" && gltfUrl ? (
                <ModelViewer gltfUrl={gltfUrl} />
              ) : isProcessing ? (
                <div className="flex flex-col items-center justify-center h-64 rounded-lg border border-dashed border-border bg-muted/30">
                  <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground mb-2" />
                  <p className="text-sm font-medium">
                    Processing your model...
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Polling every {POLL_INTERVAL_MS / 1000}s. The viewer will
                    appear once processing is complete.
                  </p>
                </div>
              ) : model.status === "FAILED" ? (
                <div className="flex flex-col items-center justify-center h-64 rounded-lg border border-dashed border-destructive/30 bg-destructive/5">
                  <AlertCircle className="h-8 w-8 text-destructive mb-2" />
                  <p className="text-sm font-medium text-destructive">
                    Processing failed
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    There was an error processing this model. Please try
                    re-uploading.
                  </p>
                </div>
              ) : (
                <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border bg-muted/30">
                  <p className="text-sm text-muted-foreground">
                    Viewer not available for current status: {model.status}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Actions panel */}
        <Card className="border-border bg-card">
          <CardHeader>
            <CardTitle className="text-base font-semibold">Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="w-full">
                    {isSTL ? (
                      <Button className="w-full" disabled>
                        <Cog className="mr-2 h-4 w-4" />
                        Open Workspace
                      </Button>
                    ) : (
                      <Button
                        className="w-full"
                        asChild
                        disabled={model.status !== "READY"}
                      >
                        <Link to={`/models/${model.id}/workspace`}>
                          <Cog className="mr-2 h-4 w-4" />
                          Open Workspace
                        </Link>
                      </Button>
                    )}
                  </span>
                </TooltipTrigger>
                {isSTL && (
                  <TooltipContent>
                    <p>
                      Workspace requires B-Rep format (STEP/IGES).
                      <br />
                      STL does not support feature recognition.
                    </p>
                  </TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
            <Button className="w-full" disabled={model.status !== "READY"}>
              Request RFQ
            </Button>
            <Button variant="outline" className="w-full">
              Download CAD File
            </Button>
            <Button variant="outline" className="w-full">
              Share Model
            </Button>
            <Separator />
            <Button variant="destructive" className="w-full">
              Delete Model
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Geometry Summary — always shown when READY and geometry exists */}
      {model.status === "READY" && model.geometry && (
        <div className="mt-6">
          <GeometrySummaryCard geometry={model.geometry} isSTL={isSTL} />
        </div>
      )}

      {/* Feature Panel — only for non-STL models with features */}
      {model.status === "READY" &&
        !isSTL &&
        model.features &&
        model.features.length > 0 && (
          <div className="mt-6">
            <FeaturePanel features={model.features} />
          </div>
        )}
    </>
  );
}
