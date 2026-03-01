/**
 * useModelStatus — poll model processing status until READY.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { getModel, getViewerUrl } from "@/lib/models-api";
import { useWorkspaceStore } from "@/store/workspaceStore";
import type { Model } from "@/types";

const POLL_MS = 4000;

export function useModelStatus(modelId: string | undefined) {
  const [model, setModel] = useState<Model | null>(null);
  const [loading, setLoading] = useState(true);
  const { setGltfUrl, setModelName } = useWorkspaceStore();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchModel = useCallback(async () => {
    if (!modelId) return;
    try {
      const data = await getModel(modelId);
      setModel(data);
      setModelName(data.name);

      if (data.status === "READY") {
        try {
          const viewer = await getViewerUrl(modelId);
          setGltfUrl(viewer.gltf_url);
        } catch {
          // viewer URL may fail
        }
      }
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, [modelId, setGltfUrl, setModelName]);

  useEffect(() => {
    fetchModel();
  }, [fetchModel]);

  // Polling for PROCESSING
  useEffect(() => {
    if (!model || (model.status !== "PROCESSING" && model.status !== "UPLOADED")) {
      return;
    }
    pollRef.current = setInterval(fetchModel, POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [model?.status, fetchModel]);

  return { model, loading };
}
