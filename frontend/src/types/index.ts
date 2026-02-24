// ─── User & Auth ─────────────────────────────────────────────────────────────

export type UserRole = "USER" | "VENDOR" | "ADMIN";

export interface User {
    id: string;
    email: string;
    name: string;
    role: UserRole;
}

export interface AuthState {
    user: User | null;
    role: UserRole | null;
    token: string | null;
    isAuthenticated: boolean;
}

export interface LoginCredentials {
    email: string;
    password: string;
}

export interface RegisterCredentials {
    name: string;
    email: string;
    password: string;
    role: UserRole;
}

// ─── Models ──────────────────────────────────────────────────────────────────

export type ModelStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";
export type ModelVisibility = "PRIVATE" | "PUBLIC";

export interface Model {
    id: string;
    user_id: string;
    name: string;
    original_filename: string;
    file_format: string;
    version: number;
    status: ModelStatus;
    visibility: ModelVisibility;
    created_at: string;
}

// ─── API Request / Response Types ────────────────────────────────────────────

export interface UploadRequest {
    filename: string;
    file_format: string;
    name?: string;
}

export interface UploadResponse {
    model_id: string;
    signed_url: string;
    gcs_path: string;
}

export interface ConfirmUploadRequest {
    model_id: string;
}

export interface ModelListResponse {
    models: Model[];
    total: number;
}

export interface ViewerUrlResponse {
    model_id: string;
    gltf_url: string;
    expires_in_seconds: number;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
    user: {
        id: string;
        email: string;
        name: string;
        role: UserRole;
        created_at: string;
    };
}

// ─── Vendor ──────────────────────────────────────────────────────────────────

export interface VendorProfile {
    id: string;
    companyName: string;
    machines: string[];
    materials: string[];
    maxPartSize: string;
    toleranceCapability: string;
    approved: boolean;
}

// ─── RFQ ─────────────────────────────────────────────────────────────────────

export type RfqStatus = "PENDING" | "QUOTED" | "ACCEPTED" | "REJECTED";

export interface Rfq {
    id: string;
    modelId: string;
    modelName: string;
    quantity: number;
    status: RfqStatus;
    createdAt: string;
    dueDate: string;
}

// ─── Navigation ──────────────────────────────────────────────────────────────

export interface NavItem {
    title: string;
    href: string;
    icon: string;
    badge?: string;
}
