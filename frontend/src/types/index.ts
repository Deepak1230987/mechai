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

export type ModelStatus = "UPLOADED" | "PROCESSING" | "READY";
export type ModelVisibility = "PRIVATE" | "PUBLIC";

export interface Model {
    id: string;
    name: string;
    version: number;
    status: ModelStatus;
    visibility: ModelVisibility;
    createdAt: string;
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
