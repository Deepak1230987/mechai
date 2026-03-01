/**
 * WorkspaceLayout — grid layout for the ModelWorkspace page.
 *
 * ┌──────────┬───────────────────────┬──────────────────┐
 * │ Sidebar  │ 3D Viewer             │ Chat Panel       │
 * │          │                       │                  │
 * │          ├───────────────────────┤──────────────────┤
 * │          │ Operation Timeline    │ Strategy + Cost  │
 * │          ├───────────────────────┴──────────────────┤
 * │          │ Version History + RFQ + Risk             │
 * └──────────┴──────────────────────────────────────────┘
 */

import type { ReactNode } from "react";

interface WorkspaceLayoutProps {
  sidebar: ReactNode;
  viewer: ReactNode;
  chat: ReactNode;
  timeline: ReactNode;
  strategyCost: ReactNode;
  bottomBar: ReactNode;
}

export function WorkspaceLayout({
  sidebar,
  viewer,
  chat,
  timeline,
  strategyCost,
  bottomBar,
}: WorkspaceLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="hidden lg:flex lg:w-56 lg:flex-col lg:border-r border-border flex-shrink-0">
        {sidebar}
      </aside>

      {/* Main grid */}
      <div className="flex-1 grid grid-rows-[1fr_auto_auto] grid-cols-1 lg:grid-cols-[1fr_360px] overflow-hidden">
        {/* Row 1 Left: 3D Viewer */}
        <div className="min-h-0 overflow-hidden border-b border-border">
          {viewer}
        </div>

        {/* Row 1 Right: Chat Panel */}
        <div className="hidden lg:flex min-h-0 overflow-hidden border-b border-l border-border">
          {chat}
        </div>

        {/* Row 2 Left: Operation Timeline */}
        <div className="min-h-0 overflow-auto border-b border-border">
          {timeline}
        </div>

        {/* Row 2 Right: Strategy + Cost */}
        <div className="hidden lg:flex min-h-0 overflow-auto border-b border-l border-border">
          {strategyCost}
        </div>

        {/* Row 3: Bottom bar spanning full width */}
        <div className="col-span-full min-h-0 overflow-auto">{bottomBar}</div>
      </div>
    </div>
  );
}
