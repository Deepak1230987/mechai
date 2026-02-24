import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type {
  User,
  LoginCredentials,
  RegisterCredentials,
  UserRole,
} from "@/types";
import { AuthContext, type AuthContextValue } from "@/context/auth-context";
import { loginApi, registerApi, getMeApi } from "@/lib/auth-api";

// Re-export so existing imports still work
export { AuthContext } from "@/context/auth-context";

// ─── Provider ────────────────────────────────────────────────────────────────

const TOKEN_KEY = "token";

/**
 * Decode the JWT payload to extract user info.
 * This is a lightweight decode (no verification — gateway does that).
 */
function decodeTokenPayload(
  token: string,
): { sub: string; role: UserRole } | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return { sub: payload.sub, role: payload.role };
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount: if token exists, fetch the current user profile
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    const decoded = decodeTokenPayload(token);
    if (!decoded) {
      localStorage.removeItem(TOKEN_KEY);
      setIsLoading(false);
      return;
    }
    // Try to hydrate user from /auth/me
    getMeApi()
      .then((u) => setUser(u))
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    const res = await loginApi(credentials);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    setUser({
      id: res.user.id,
      email: res.user.email,
      name: res.user.name,
      role: res.user.role,
    });
  }, []);

  const register = useCallback(async (credentials: RegisterCredentials) => {
    const res = await registerApi(credentials);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    setUser({
      id: res.user.id,
      email: res.user.email,
      name: res.user.name,
      role: res.user.role,
    });
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
      isLoading,
      login,
      register,
      logout,
    }),
    [user, isLoading, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
