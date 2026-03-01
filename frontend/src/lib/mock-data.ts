import type { Model, VendorProfile, Rfq, User } from "@/types";

// ─── Mock Users (used for auth simulation) ───────────────────────────────────

export const MOCK_USERS: Record<string, User & { password: string }> = {
    "user@example.com": {
        id: "u1",
        email: "user@example.com",
        name: "John User",
        role: "USER",
        password: "password123",
    },
    "vendor@example.com": {
        id: "v1",
        email: "vendor@example.com",
        name: "Jane Vendor",
        role: "VENDOR",
        password: "password123",
    },
    "admin@example.com": {
        id: "a1",
        email: "admin@example.com",
        name: "Admin Smith",
        role: "ADMIN",
        password: "password123",
    },
};

// ─── Mock JWT tokens (base64 encoded payloads) ───────────────────────────────

function createMockToken(user: User): string {
    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(
        JSON.stringify({
            sub: user.id,
            email: user.email,
            name: user.name,
            role: user.role,
            exp: Math.floor(Date.now() / 1000) + 86400, // 24h
        })
    );
    const signature = btoa("mock-signature");
    return `${header}.${payload}.${signature}`;
}

export function getMockToken(email: string): string | null {
    const user = MOCK_USERS[email];
    if (!user) return null;
    return createMockToken(user);
}

export function decodeMockToken(token: string): User | null {
    try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        return {
            id: payload.sub,
            email: payload.email,
            name: payload.name,
            role: payload.role,
        };
    } catch {
        return null;
    }
}

// ─── Mock Models ─────────────────────────────────────────────────────────────

export const MOCK_MODELS: Model[] = [
    {
        id: "m1",
        user_id: "u1",
        name: "Bracket Assembly v2",
        original_filename: "bracket_v2.step",
        file_format: "STEP",
        version: 2,
        status: "FAILED",
        visibility: "PRIVATE",
        created_at: new Date(Date.now() - 172800000).toISOString(),
        updated_at: new Date(Date.now() - 172000000).toISOString(),
        thumbnail_url: null,
    },
    {
        id: "m2",
        user_id: "u1",
        name: "Motor Mount",
        original_filename: "motor_mount.step",
        file_format: "STEP",
        version: 1,
        status: "PROCESSING",
        visibility: "PRIVATE",
        created_at: new Date(Date.now() - 3600000).toISOString(),
        updated_at: new Date(Date.now() - 1800000).toISOString(),
        thumbnail_url: null,
    },
    {
        id: "m3",
        user_id: "u1",
        name: "Sensor Housing",
        original_filename: "sensor_housing.step",
        file_format: "STEP",
        version: 3,
        status: "UPLOADED",
        visibility: "PUBLIC",
        created_at: new Date(Date.now() - 259200000).toISOString(),
        updated_at: new Date(Date.now() - 200000000).toISOString(),
        thumbnail_url: null,
    },
    {
        id: "m4",
        user_id: "u1",
        name: "Robotic Arm Link",
        original_filename: "arm_link.step",
        file_format: "STEP",
        version: 1,
        status: "READY",
        visibility: "PUBLIC",
        created_at: new Date(Date.now() - 86400000).toISOString(),
        updated_at: new Date(Date.now() - 43200000).toISOString(),
        thumbnail_url: null,
    },
    {
        id: "m5",
        user_id: "u1",
        name: "Heat Sink Custom",
        original_filename: "heatsink.step",
        file_format: "STEP",
        version: 2,
        status: "PROCESSING",
        visibility: "PRIVATE",
        created_at: new Date(Date.now() - 129600000).toISOString(),
        updated_at: new Date(Date.now() - 100000000).toISOString(),
        thumbnail_url: null,
    },
];

// ─── Mock Vendor Profiles ────────────────────────────────────────────────────

export const MOCK_VENDORS: VendorProfile[] = [
    {
        id: "v1",
        companyName: "PrecisionCNC Co.",
        machines: ["3-Axis CNC", "5-Axis CNC", "CNC Lathe"],
        materials: ["Aluminum 6061", "Steel 304", "Titanium Ti-6Al-4V"],
        maxPartSize: "500x500x300 mm",
        toleranceCapability: "±0.01 mm",
        approved: true,
    },
    {
        id: "v2",
        companyName: "RapidMach Industries",
        machines: ["3-Axis CNC", "Wire EDM"],
        materials: ["Aluminum 7075", "Brass", "Copper"],
        maxPartSize: "300x300x200 mm",
        toleranceCapability: "±0.05 mm",
        approved: false,
    },
    {
        id: "v3",
        companyName: "MetalWorks Pro",
        machines: ["5-Axis CNC", "CNC Mill", "Surface Grinder"],
        materials: ["Steel 316", "Inconel 718", "Aluminum 2024"],
        maxPartSize: "800x600x400 mm",
        toleranceCapability: "±0.005 mm",
        approved: true,
    },
];

// ─── Mock RFQs ───────────────────────────────────────────────────────────────

export const MOCK_RFQS: Rfq[] = [
    {
        id: "rfq1",
        modelId: "m1",
        modelName: "Bracket Assembly v2",
        quantity: 100,
        status: "PENDING",
        createdAt: "2026-02-21T08:00:00Z",
        dueDate: "2026-03-07T00:00:00Z",
    },
    {
        id: "rfq2",
        modelId: "m4",
        modelName: "Gearbox Plate",
        quantity: 50,
        status: "QUOTED",
        createdAt: "2026-02-19T12:00:00Z",
        dueDate: "2026-03-05T00:00:00Z",
    },
    {
        id: "rfq3",
        modelId: "m3",
        modelName: "Housing Cap",
        quantity: 200,
        status: "ACCEPTED",
        createdAt: "2026-02-15T09:30:00Z",
        dueDate: "2026-03-01T00:00:00Z",
    },
    {
        id: "rfq4",
        modelId: "m1",
        modelName: "Bracket Assembly v2",
        quantity: 25,
        status: "REJECTED",
        createdAt: "2026-02-20T15:00:00Z",
        dueDate: "2026-03-10T00:00:00Z",
    },
];
