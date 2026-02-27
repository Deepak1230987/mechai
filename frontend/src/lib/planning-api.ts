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
