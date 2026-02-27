/**
 * Planning API service — machining plan CRUD calls.
 * All requests go through the API Gateway.
 */

import api from "@/lib/api";
import type {
    MachiningPlan,
    PlanUpdateRequest,
    PlanUpdateResponse,
    PlanApproveRequest,
    VersionSummary,
} from "@/types/machining";

/** Request payload for plan generation. */
export interface GeneratePlanRequest {
    model_id: string;
    material: string;
    machine_type: string;
}

/** Fetch the latest (highest-version) plan for a model. Returns null if 404. */
export async function getLatestPlan(modelId: string): Promise<MachiningPlan | null> {
    try {
        const { data } = await api.get<MachiningPlan>(
            `/planning/${modelId}/latest`,
        );
        return data;
    } catch (err: unknown) {
        // 404 = no plan generated yet — not an error, just empty state
        if (
            typeof err === "object" &&
            err !== null &&
            "response" in err &&
            typeof (err as { response?: { status?: number } }).response?.status === "number" &&
            (err as { response: { status: number } }).response.status === 404
        ) {
            return null;
        }
        throw err;
    }
}

/** Generate a new machining plan via the hybrid pipeline. */
export async function generatePlan(
    payload: GeneratePlanRequest,
): Promise<MachiningPlan> {
    const { data } = await api.post<MachiningPlan>(
        "/planning/generate",
        payload,
    );
    return data;
}

// ─── Version Navigation ──────────────────────────────────────────────────────

/** Fetch lightweight summaries of all plan versions for a model. */
export async function listVersions(modelId: string): Promise<VersionSummary[]> {
    const { data } = await api.get<VersionSummary[]>(
        `/planning/${modelId}/versions`,
    );
    return data;
}

/** Fetch a specific plan version by version number. */
export async function getVersion(
    modelId: string,
    versionNum: number,
): Promise<MachiningPlan> {
    const { data } = await api.get<MachiningPlan>(
        `/planning/${modelId}/version/${versionNum}`,
    );
    return data;
}

/** Submit a human edit — creates a new immutable version. */
export async function updatePlan(
    planId: string,
    payload: PlanUpdateRequest,
): Promise<PlanUpdateResponse> {
    const { data } = await api.post<PlanUpdateResponse>(
        `/planning/${planId}/update`,
        payload,
    );
    return data;
}

/** Approve a plan for RFQ eligibility. */
export async function approvePlan(
    planId: string,
    payload: PlanApproveRequest,
): Promise<MachiningPlan> {
    const { data } = await api.post<MachiningPlan>(
        `/planning/${planId}/approve`,
        payload,
    );
    return data;
}

// ─── Copilot Chat ────────────────────────────────────────────────────────────

/** Request payload for chat refinement. */
export interface ChatRequest {
    user_message: string;
}

/** Response from the copilot chat endpoint. */
export interface ChatResponse {
    type: "conversation" | "plan_update" | "plan_proposal";
    message?: string;
    explanation?: string;
    machining_plan?: MachiningPlan;
    proposed_plan?: MachiningPlan;
    version?: number;
}

/** Send a message to the Machining Copilot to refine the plan. */
export async function chatRefinePlan(
    planId: string,
    payload: ChatRequest,
): Promise<ChatResponse> {
    const { data } = await api.post<ChatResponse>(
        `/planning/${planId}/chat`,
        payload,
    );
    return data;
}

// ─── PDF Export ──────────────────────────────────────────────────────────────

/** Request payload for PDF export. */
export interface ExportRequest {
    company_name?: string;
    part_name?: string;
    include_narrative?: boolean;
}

/**
 * Export the machining plan as a PDF process sheet.
 * Returns a Blob that can be downloaded in the browser.
 */
export async function exportPlanPdf(
    planId: string,
    payload: ExportRequest = {},
): Promise<Blob> {
    const { data } = await api.post(
        `/planning/${planId}/export`,
        payload,
        { responseType: "blob" },
    );
    return data as Blob;
}
