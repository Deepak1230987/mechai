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
      {/* Brand */}
      <div className="flex h-16 items-center border-b border-sidebar-border px-5">
        <Link
          to="/"
          className="flex items-center gap-2.5 font-semibold text-base tracking-tight"
          onClick={onNavigate}
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Box className="h-4 w-4 text-primary-foreground" />
          </div>
          <span>AI-CAM-RFQ</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 px-3 py-4">
        <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-foreground/40">
          Navigation
        </p>
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
                "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground",
              )}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.75 rounded-r-sm bg-primary" />
              )}
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{item.title}</span>
              {item.badge && (
                <Badge
                  variant="secondary"
                  className="ml-auto h-5 min-w-5 justify-center rounded px-1.5 text-[10px] font-semibold"
                >
                  {item.badge}
                </Badge>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-sidebar-border px-5 py-3">
        <div className="flex items-center gap-2 text-[11px] text-sidebar-foreground/40">
          <Settings className="h-3 w-3" />
          <span>v0.1.0 — Phase 1</span>
        </div>
      </div>
    </div>
  );
}
