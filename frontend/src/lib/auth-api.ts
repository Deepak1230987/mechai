/**
 * Auth API service — calls POST /auth/login, POST /auth/register, GET /auth/me
 */

import api from "@/lib/api";
import type { LoginCredentials, RegisterCredentials, TokenResponse, User } from "@/types";

export async function loginApi(credentials: LoginCredentials): Promise<TokenResponse> {
    const { data } = await api.post<TokenResponse>("/auth/login", credentials);
    return data;
}

export async function registerApi(credentials: RegisterCredentials): Promise<TokenResponse> {
    const { data } = await api.post<TokenResponse>("/auth/register", credentials);
    return data;
}

export async function getMeApi(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return {
        id: data.id,
        email: data.email,
        name: data.name,
        role: data.role,
    } as User;
}
