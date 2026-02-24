import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { User, LoginCredentials, RegisterCredentials } from "@/types";
import { MOCK_USERS, getMockToken, decodeMockToken } from "@/lib/mock-data";
import { AuthContext, type AuthContextValue } from "@/context/auth-context";

// Re-export so existing imports still work
export { AuthContext } from "@/context/auth-context";

// ─── Provider ────────────────────────────────────────────────────────────────

const TOKEN_KEY = "token";

function hydrateUser() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    const decoded = decodeMockToken(token);
    if (decoded) return decoded;
    localStorage.removeItem(TOKEN_KEY);
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => hydrateUser());

  const login = useCallback(async (credentials: LoginCredentials) => {
    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 500));

    const mockUser = MOCK_USERS[credentials.email];
    if (!mockUser || mockUser.password !== credentials.password) {
      throw new Error("Invalid email or password");
    }

    const token = getMockToken(credentials.email);
    if (!token) throw new Error("Token generation failed");

    localStorage.setItem(TOKEN_KEY, token);
    const decoded = decodeMockToken(token);
    setUser(decoded);
  }, []);

  const register = useCallback(async (credentials: RegisterCredentials) => {
    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 500));

    // In mock mode, just check if user doesn't already exist
    if (MOCK_USERS[credentials.email]) {
      throw new Error("User already exists");
    }

    // For mock: create a token for the new user
    const newUser: User = {
      id: `u-${Date.now()}`,
      email: credentials.email,
      name: credentials.name,
      role: credentials.role,
    };

    const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
    const payload = btoa(
      JSON.stringify({
        sub: newUser.id,
        email: newUser.email,
        name: newUser.name,
        role: newUser.role,
        exp: Math.floor(Date.now() / 1000) + 86400,
      }),
    );
    const signature = btoa("mock-signature");
    const token = `${header}.${payload}.${signature}`;

    localStorage.setItem(TOKEN_KEY, token);
    setUser(newUser);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role: user?.role ?? null,
      isAuthenticated: !!user,
      isLoading: false,
      login,
      register,
      logout,
    }),
    [user, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
