/**
 * Models API service — all CAD model related calls.
 * All requests go through the API Gateway which injects user context.
 */

import axios from "axios";
import api from "@/lib/api";
import type {
    Model,
    ModelListResponse,
    UploadResponse,
    ViewerUrlResponse,
} from "@/types";

/**
 * Step 1: Request a signed upload URL from the backend.
 */
export async function requestUploadUrl(
    filename: string,
    fileFormat: string,
    name?: string,
): Promise<UploadResponse> {
    const { data } = await api.post<UploadResponse>("/models/upload", {
        filename,
        file_format: fileFormat,
        name,
    });
    return data;
}

/**
 * Step 2: Upload the file directly to the signed URL (Cloud Storage).
 * Uses a raw axios instance (no auth header, no base URL).
 */
export async function uploadFileToSignedUrl(
    signedUrl: string,
    file: File,
    onProgress?: (percent: number) => void,
): Promise<void> {
    await axios.put(signedUrl, file, {
        headers: { "Content-Type": "application/octet-stream" },
        onUploadProgress: (event) => {
            if (event.total && onProgress) {
                onProgress(Math.round((event.loaded / event.total) * 100));
            }
        },
    });
}

/**
 * Step 3: Confirm the upload to trigger processing.
 */
export async function confirmUpload(modelId: string): Promise<Model> {
    const { data } = await api.post<Model>("/models/confirm-upload", {
        model_id: modelId,
    });
    return data;
}

/**
 * List the current user's models.
 */
export async function listModels(skip = 0, limit = 50): Promise<ModelListResponse> {
    const { data } = await api.get<ModelListResponse>("/models/", {
        params: { skip, limit },
    });
    return data;
}

/**
 * Get a single model by ID.
 */
export async function getModel(modelId: string): Promise<Model> {
    const { data } = await api.get<Model>(`/models/${modelId}`);
    return data;
}

/**
 * Get the signed glTF viewer URL (only works if status === READY).
 */
export async function getViewerUrl(modelId: string): Promise<ViewerUrlResponse> {
    const { data } = await api.get<ViewerUrlResponse>(`/models/${modelId}/viewer`);
    return data;
}
