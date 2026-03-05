/**
 * Intelligence API — calls Phase C endpoints on the AI Service.
 * All requests go through the API Gateway → /intelligence/...
 */

import api from "@/lib/api";
import type {
    CostBreakdown,
    TimeBreakdown,
    SpatialOperationMap,
    MachiningPacket,
    RFQPacket,
    ImpactResult,
    FeatureExplanation,
    OperationExplanation,
    IntelligenceResponse,
} from "@/types/intelligence";

// ─── Query ───────────────────────────────────────────────────────────────────

export interface IntelligenceQueryRequest {
    user_message: string;
    plan_id?: string;
    version?: number;
    part_name?: string;
}

export async function queryIntelligence(
    modelId: string,
    payload: IntelligenceQueryRequest,
): Promise<IntelligenceResponse> {
    const { data } = await api.post<IntelligenceResponse>(
        `/intelligence/${modelId}/query`,
        payload,
    );
    return data;
}

// ─── Narrative ───────────────────────────────────────────────────────────────

export interface NarrativeData {
    sections: { title: string; icon: string; content: string }[];
    full_text: string;
    model_id: string;
    plan_id: string;
    version: number;
    strategy: string;
}

export async function getNarrative(
    modelId: string,
    version?: number,
): Promise<IntelligenceResponse<NarrativeData>> {
    const params = version ? { version } : {};
    const { data } = await api.get<IntelligenceResponse<NarrativeData>>(
        `/intelligence/${modelId}/narrative`,
        { params },
    );
    return data;
}

// ─── Cost ────────────────────────────────────────────────────────────────────

export async function getCostBreakdown(
    modelId: string,
    version?: number,
    strategy?: string,
): Promise<IntelligenceResponse<CostBreakdown>> {
    const params: Record<string, unknown> = {};
    if (version) params.version = version;
    if (strategy) params.strategy = strategy;
    const { data } = await api.get<IntelligenceResponse<CostBreakdown>>(
        `/intelligence/${modelId}/cost`,
        { params },
    );
    return data;
}

// ─── Time ────────────────────────────────────────────────────────────────────

export async function getTimeBreakdown(
    modelId: string,
    version?: number,
    strategy?: string,
): Promise<IntelligenceResponse<TimeBreakdown>> {
    const params: Record<string, unknown> = {};
    if (version) params.version = version;
    if (strategy) params.strategy = strategy;
    const { data } = await api.get<IntelligenceResponse<TimeBreakdown>>(
        `/intelligence/${modelId}/time`,
        { params },
    );
    return data;
}

// ─── Spatial ─────────────────────────────────────────────────────────────────

export async function getSpatialMap(
    modelId: string,
    version?: number,
): Promise<IntelligenceResponse<SpatialOperationMap>> {
    const params = version ? { version } : {};
    const { data } = await api.get<IntelligenceResponse<SpatialOperationMap>>(
        `/intelligence/${modelId}/spatial`,
        { params },
    );
    return data;
}

// ─── Machining Packet ────────────────────────────────────────────────────────

export async function getMachiningPacket(
    modelId: string,
    version?: number,
): Promise<IntelligenceResponse<MachiningPacket>> {
    const params = version ? { version } : {};
    const { data } = await api.get<IntelligenceResponse<MachiningPacket>>(
        `/intelligence/${modelId}/packet`,
        { params },
    );
    return data;
}

// ─── RFQ ─────────────────────────────────────────────────────────────────────

export interface RFQRequest {
    part_name?: string;
    quantity?: number;
    lot_size?: number;
    urgency?: "STANDARD" | "EXPEDITED" | "RUSH";
    special_instructions?: string[];
    plan_id?: string;
    version?: number;
}

export async function generateRFQ(
    modelId: string,
    payload: RFQRequest = {},
): Promise<IntelligenceResponse<RFQPacket>> {
    const { data } = await api.post<IntelligenceResponse<RFQPacket>>(
        `/intelligence/${modelId}/rfq`,
        payload,
    );
    return data;
}

// ─── Impact ──────────────────────────────────────────────────────────────────

export interface ImpactRequest {
    scenario: string;
    plan_id?: string;
    version?: number;
}

export async function simulateImpact(
    modelId: string,
    payload: ImpactRequest,
): Promise<IntelligenceResponse<ImpactResult>> {
    const { data } = await api.post<IntelligenceResponse<ImpactResult>>(
        `/intelligence/${modelId}/impact`,
        payload,
    );
    return data;
}

// ─── Explanations ────────────────────────────────────────────────────────────

export async function explainFeature(
    modelId: string,
    featureId: string,
    version?: number,
): Promise<IntelligenceResponse<FeatureExplanation>> {
    const params = version ? { version } : {};
    const { data } = await api.get<IntelligenceResponse<FeatureExplanation>>(
        `/intelligence/${modelId}/explain/feature/${featureId}`,
        { params },
    );
    return data;
}

export async function explainOperation(
    modelId: string,
    operationId: string,
    version?: number,
): Promise<IntelligenceResponse<OperationExplanation>> {
    const params = version ? { version } : {};
    const { data } = await api.get<IntelligenceResponse<OperationExplanation>>(
        `/intelligence/${modelId}/explain/operation/${operationId}`,
        { params },
    );
    return data;
}

// ─── Industrial PDF ──────────────────────────────────────────────────────────

export interface IndustrialPDFRequest {
    part_name?: string;
    company_name?: string;
    include_cost?: boolean;
    include_time?: boolean;
    include_risk?: boolean;
    include_strategy?: boolean;
    include_revision_history?: boolean;
    plan_id?: string;
    version?: number;
}

export async function downloadIndustrialPDF(
    modelId: string,
    payload: IndustrialPDFRequest = {},
): Promise<Blob> {
    const { data } = await api.post(
        `/intelligence/${modelId}/industrial-pdf`,
        payload,
        { responseType: "blob" },
    );
    return data as Blob;
}

// ─── Rollback ────────────────────────────────────────────────────────────────

export async function rollbackPlan(
    modelId: string,
    targetVersion: number,
): Promise<unknown> {
    const { data } = await api.post(
        `/planning/${modelId}/rollback`,
        { target_version: targetVersion },
    );
    return data;
}

// ─── Versions ────────────────────────────────────────────────────────────────

export async function listVersions(
    modelId: string,
): Promise<unknown[]> {
    const { data } = await api.get(`/planning/${modelId}/versions`);
    return data as unknown[];
}
