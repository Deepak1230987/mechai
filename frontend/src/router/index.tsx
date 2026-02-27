import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { ProtectedRoute } from "@/components/shared/ProtectedRoute";
import { RoleGuard } from "@/components/shared/RoleGuard";

// Auth pages
import { LoginPage } from "@/pages/auth/LoginPage";
import { RegisterPage } from "@/pages/auth/RegisterPage";

// User pages
import { DashboardPage } from "@/pages/dashboard/DashboardPage";
import { ModelsPage } from "@/pages/dashboard/ModelsPage";
import { ModelUploadPage } from "@/pages/dashboard/ModelUploadPage";
import { ModelDetailPage } from "@/pages/dashboard/ModelDetailPage";
import { MachiningPlanPage } from "@/pages/dashboard/MachiningPlanPage";

// Vendor pages
import { VendorDashboardPage } from "@/pages/vendor/VendorDashboardPage";
import { VendorProfilePage } from "@/pages/vendor/VendorProfilePage";
import { VendorRfqsPage } from "@/pages/vendor/VendorRfqsPage";

// Admin pages
import { AdminDashboardPage } from "@/pages/admin/AdminDashboardPage";
import { AdminVendorsPage } from "@/pages/admin/AdminVendorsPage";
import { AdminModelsPage } from "@/pages/admin/AdminModelsPage";

export const router = createBrowserRouter([
  // ─── Public Routes ─────────────────────────────────────────────────────────
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/register",
    element: <RegisterPage />,
  },

  // ─── Protected Routes (inside AppLayout) ───────────────────────────────────
  {
    element: (
      <ProtectedRoute>
        <AppLayout />
      </ProtectedRoute>
    ),
    children: [
      // ── USER routes ──────────────────────────────────────────────────────
      {
        path: "/dashboard",
        element: (
          <RoleGuard allowedRoles={["USER"]}>
            <DashboardPage />
          </RoleGuard>
        ),
      },
      {
        path: "/models",
        element: (
          <RoleGuard allowedRoles={["USER"]}>
            <ModelsPage />
          </RoleGuard>
        ),
      },
      {
        path: "/models/upload",
        element: (
          <RoleGuard allowedRoles={["USER"]}>
            <ModelUploadPage />
          </RoleGuard>
        ),
      },
      {
        path: "/models/:id",
        element: (
          <RoleGuard allowedRoles={["USER"]}>
            <ModelDetailPage />
          </RoleGuard>
        ),
      },
      {
        path: "/models/:modelId/plan",
        element: (
          <RoleGuard allowedRoles={["USER"]}>
            <MachiningPlanPage />
          </RoleGuard>
        ),
      },

      // ── VENDOR routes ────────────────────────────────────────────────────
      {
        path: "/vendor",
        element: (
          <RoleGuard allowedRoles={["VENDOR"]}>
            <VendorDashboardPage />
          </RoleGuard>
        ),
      },
      {
        path: "/vendor/profile",
        element: (
          <RoleGuard allowedRoles={["VENDOR"]}>
            <VendorProfilePage />
          </RoleGuard>
        ),
      },
      {
        path: "/vendor/rfqs",
        element: (
          <RoleGuard allowedRoles={["VENDOR"]}>
            <VendorRfqsPage />
          </RoleGuard>
        ),
      },

      // ── ADMIN routes ─────────────────────────────────────────────────────
      {
        path: "/admin",
        element: (
          <RoleGuard allowedRoles={["ADMIN"]}>
            <AdminDashboardPage />
          </RoleGuard>
        ),
      },
      {
        path: "/admin/vendors",
        element: (
          <RoleGuard allowedRoles={["ADMIN"]}>
            <AdminVendorsPage />
          </RoleGuard>
        ),
      },
      {
        path: "/admin/models",
        element: (
          <RoleGuard allowedRoles={["ADMIN"]}>
            <AdminModelsPage />
          </RoleGuard>
        ),
      },
    ],
  },

  // ─── Catch-all redirect ────────────────────────────────────────────────────
  {
    path: "*",
    element: <Navigate to="/login" replace />,
  },
]);
