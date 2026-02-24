import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { getNavItems } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  LayoutDashboard,
  Box,
  Upload,
  Building2,
  FileText,
  Users,
  Settings,
  type LucideIcon,
} from "lucide-react";

const iconMap: Record<string, LucideIcon> = {
  LayoutDashboard,
  Box,
  Upload,
  Building2,
  FileText,
  Users,
  Settings,
};

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  const { role } = useAuth();
  const location = useLocation();

  if (!role) return null;

  const navItems = getNavItems(role);

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo / Brand */}
      <div className="flex h-14 items-center border-b border-sidebar-border px-4">
        <Link
          to="/"
          className="flex items-center gap-2 font-semibold text-lg"
          onClick={onNavigate}
        >
          <Box className="h-6 w-6 text-sidebar-primary" />
          <span>AI-CAM-RFQ</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {navItems.map((item) => {
          const Icon = iconMap[item.icon] ?? LayoutDashboard;
          const isActive =
            location.pathname === item.href ||
            (item.href !== "/" &&
              item.href !== "/dashboard" &&
              item.href !== "/vendor" &&
              item.href !== "/admin" &&
              location.pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              to={item.href}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{item.title}</span>
              {item.badge && (
                <Badge variant="secondary" className="ml-auto text-xs">
                  {item.badge}
                </Badge>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border p-3">
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-sidebar-foreground/50">
          <Settings className="h-3.5 w-3.5" />
          <span>v0.1.0 — Phase 1</span>
        </div>
      </div>
    </div>
  );
}
