// ─── Machining Plan Types ────────────────────────────────────────────────────
// Strict TypeScript types matching the backend MachiningPlanResponse schema.
// No `any` — every field is explicitly typed.

export interface Tool {
    id: string;
    type: ToolType;
    diameter: number;
    max_depth: number;
    recommended_rpm_min: number;
    recommended_rpm_max: number;
}

export type ToolType =
    | "DRILL"
    | "FLAT_END_MILL"
    | "BALL_END_MILL"
    | "SLOT_CUTTER"
    | "TURNING_INSERT";

export interface OperationParameters {
    feed_rate?: number;
    spindle_speed?: number;
    stepover?: number;
    depth_of_cut?: number;
    [key: string]: number | string | boolean | undefined;
}

export interface Operation {
    id: string;
    feature_id: string;
    type: OperationType;
    tool_id: string;
    parameters: OperationParameters;
    estimated_time: number;
}

export type OperationType =
    | "DRILLING"
    | "POCKET_ROUGHING"
    | "POCKET_FINISHING"
    | "SLOT_MILLING"
    | "ROUGH_TURNING"
    | "FINISH_TURNING"
    | "FACE_MILLING";

export interface Setup {
    setup_id: string;
    orientation: string;
    operations: string[]; // ordered operation IDs
}

export interface MachiningPlan {
    plan_id: string | null;
    model_id: string;
    material: string;
    machine_type: MachineType;
    setups: Setup[];
    operations: Operation[];
    tools: Tool[];
    estimated_time: number;
    version: number;
    approved: boolean;
    approved_by: string | null;
    approved_at: string | null;
}

export type MachineType = "MILLING_3AXIS" | "LATHE";

// ─── API Request / Response Types ────────────────────────────────────────────

export interface PlanUpdateRequest {
    edited_plan: {
        setups: Setup[];
        operations: Operation[];
        tools: Tool[];
        estimated_time: number;
    };
    edited_by: string;
}

export interface PlanApproveRequest {
    approved_by: string;
}

export interface PlanDiff {
    operations_added: string[];
    operations_removed: string[];
    operations_changed: string[];
    tools_changed: string[];
    order_changed: boolean;
    setups_changed: boolean;
    time_delta: number;
}

export interface PlanUpdateResponse {
    plan: MachiningPlan;
    diff: PlanDiff;
    feedback_id: string;
}
