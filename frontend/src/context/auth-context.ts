import { createContext } from "react";
import type { UserRole, LoginCredentials, RegisterCredentials } from "@/types";
import type { User } from "@/types";

export interface AuthContextValue {
    user: User | null;
    role: UserRole | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (credentials: LoginCredentials) => Promise<void>;
    register: (credentials: RegisterCredentials) => Promise<void>;
    logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(
    undefined,
);
