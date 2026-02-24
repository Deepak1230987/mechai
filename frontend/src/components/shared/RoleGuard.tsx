import { Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/types";
import type { ReactNode } from "react";

interface RoleGuardProps {
  children: ReactNode;
  allowedRoles: UserRole[];
}

/**
 * Guards routes by role.
 * Redirects to the appropriate dashboard if role doesn't match.
 */
export function RoleGuard({ children, allowedRoles }: RoleGuardProps) {
  const { role } = useAuth();

  if (!role || !allowedRoles.includes(role)) {
    // Redirect to the appropriate home for their role
    const redirectPath = getRoleHomePath(role);
    return <Navigate to={redirectPath} replace />;
  }

  return <>{children}</>;
}

function getRoleHomePath(role: UserRole | null): string {
  switch (role) {
    case "VENDOR":
      return "/vendor";
    case "ADMIN":
      return "/admin";
    case "USER":
    default:
      return "/dashboard";
  }
}
