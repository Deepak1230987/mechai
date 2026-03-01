// ─── Phase C Intelligence Types ──────────────────────────────────────────────
// Matches backend ai_service Phase C schemas exactly.

// ─── Cost ────────────────────────────────────────────────────────────────────

export interface CostLineItem {
    category: string;
    description: string;
    amount: number;
    unit: string;
}

export interface CostBreakdown {
    model_id: string;
    plan_id: string;
    version: number;
    strategy: string;
    material: string;
    machine_type: string;
    machining_cost: number;
    tooling_cost: number;
    material_cost: number;
    setup_cost: number;
    overhead_cost: number;
    total_cost: number;
    line_items: CostLineItem[];
    total_time_seconds: number;
    total_time_minutes: number;
    machine_rate_per_hour: number;
    notes: string[];
}

// ─── Time ────────────────────────────────────────────────────────────────────

export interface OperationTimeDetail {
    operation_id: string;
    operation_type: string;
    feature_id: string;
    tool_id: string;
    base_time: number;
    roughing_finishing_factor: number;
    strategy_factor: number;
    complexity_factor: number;
    adjusted_time: number;
}

export interface TimeBreakdown {
    model_id: string;
    plan_id: string;
    version: number;
    strategy: string;
    first_setup_time: number;
    setup_change_count: number;
    total_setup_time: number;
    tool_change_count: number;
    total_tool_change_time: number;
    total_cutting_time: number;
    operation_details: OperationTimeDetail[];
    strategy_multiplier: number;
    complexity_multiplier: number;
    complexity_score: number;
    total_time: number;
    total_time_minutes: number;
}

// ─── Spatial ─────────────────────────────────────────────────────────────────

export interface BoundingBox3D {
    x_min: number; x_max: number;
    y_min: number; y_max: number;
    z_min: number; z_max: number;
}

export interface SpatialOperation {
    operation_id: string;
    feature_id: string;
    operation_type: string;
    setup_id: string;
    setup_orientation: string;
    tool_axis: string;
    centroid: { x: number; y: number; z: number };
    bounding_box: BoundingBox3D;
    depth: number;
    tool_id: string;
    tool_diameter: number;
    estimated_time: number;
}

export interface SetupOrientation {
    setup_id: string;
    orientation: string;
    datum_face_id: string;
    tool_axis: string;
    operation_count: number;
}

export interface SpatialOperationMap {
    model_id: string;
    plan_id: string;
    version: number;
    total_operations: number;
    spatial_operations: SpatialOperation[];
    part_bounding_box: BoundingBox3D;
    setup_orientations: SetupOrientation[];
}

// ─── Impact ──────────────────────────────────────────────────────────────────

export interface ImpactResult {
    valid: boolean;
    change_count: number;
    estimated_time_delta: number;
    estimated_cost_delta: number | null;
    new_risk_count: number;
    removed_risk_count: number;
    validation_errors: string[];
    validation_warnings: string[];
    summary: string;
    confidence: number;
    diff_json: Record<string, unknown>;
}

// ─── Explanations ────────────────────────────────────────────────────────────

export interface FeatureExplanation {
    feature_id: string;
    feature_type: string;
    dimensions: Record<string, number>;
    position: Record<string, number>;
    related_operations: string[];
    related_tools: string[];
    explanation: string;
    manufacturing_notes: string[];
    confidence: number;
}

export interface OperationExplanation {
    operation_id: string;
    operation_type: string;
    feature_id: string;
    tool_id: string;
    setup_id: string;
    parameters: Record<string, number>;
    explanation: string;
    why_this_tool: string;
    why_this_order: string;
    estimated_time: number;
    confidence: number;
}

// ─── Machining Packet ────────────────────────────────────────────────────────

export interface MachiningPacket {
    packet_version: string;
    generated_at: string;
    model_id: string;
    plan_id: string;
    version: number;
    part_name: string;
    material: string;
    machine_type: string;
    complexity_score: number;
    complexity_level: string;
    features: unknown[];
    setups: unknown[];
    operations: unknown[];
    tools: unknown[];
    risks: unknown[];
    strategies: unknown[];
    time_breakdown: Record<string, unknown> | null;
    cost_breakdown: Record<string, unknown> | null;
    selected_strategy: string;
    approved: boolean;
    approved_by: string | null;
}

// ─── RFQ Packet ──────────────────────────────────────────────────────────────

export interface RFQPacket {
    rfq_id: string;
    generated_at: string;
    status: string;
    part_name: string;
    model_id: string;
    version: number;
    quantity: number;
    lot_size: number;
    complexity_class: string;
    complexity_score: number;
    estimated_lead_time_days: number;
    urgency: string;
    manufacturing_packet: MachiningPacket;
    vendor_requirements: Record<string, unknown>;
    tolerance_specs: unknown[];
    special_instructions: string[];
}

// ─── Conversation ────────────────────────────────────────────────────────────

export interface ConversationMessage {
    id: string;
    role: "user" | "assistant";
    content: string;
    timestamp: string;
    type?: string;
    data?: unknown;
}

// ─── Strategy ────────────────────────────────────────────────────────────────

export interface StrategyVariant {
    name: string;
    description: string;
    estimated_time: number;
}

// ─── Risk ────────────────────────────────────────────────────────────────────

export interface RiskItem {
    type: string;
    severity: "LOW" | "MEDIUM" | "HIGH";
    feature_id: string;
    description: string;
}

// ─── Version ─────────────────────────────────────────────────────────────────

export interface VersionInfo {
    plan_id: string;
    version: number;
    approved: boolean;
    approved_by: string | null;
    created_at: string;
    estimated_time: number;
    operation_count: number;
    is_rollback?: boolean;
    parent_version_id?: string | null;
}

// ─── Intelligence Response ───────────────────────────────────────────────────

export interface IntelligenceResponse<T = unknown> {
    type: string;
    data: T;
    message: string;
}

// ─── Processing Status ───────────────────────────────────────────────────────

export type ProcessingStage =
    | "idle"
    | "analyzing_geometry"
    | "generating_plan"
    | "optimizing"
    | "generating_pdf"
    | "submitting_rfq"
    | "simulating_impact";
