import type { NavItem, UserRole } from "@/types";

export function getNavItems(role: UserRole): NavItem[] {
    switch (role) {
        case "USER":
            return [
                { title: "Dashboard", href: "/dashboard", icon: "LayoutDashboard" },
                { title: "Models", href: "/models", icon: "Box" },
                { title: "Upload Model", href: "/models/upload", icon: "Upload" },
            ];
        case "VENDOR":
            return [
                { title: "Dashboard", href: "/vendor", icon: "LayoutDashboard" },
                { title: "Profile", href: "/vendor/profile", icon: "Building2" },
                { title: "RFQs", href: "/vendor/rfqs", icon: "FileText", badge: "3" },
            ];
        case "ADMIN":
            return [
                { title: "Dashboard", href: "/admin", icon: "LayoutDashboard" },
                { title: "Vendors", href: "/admin/vendors", icon: "Users" },
                { title: "Models", href: "/admin/models", icon: "Box" },
            ];
        default:
            return [];
    }
}
