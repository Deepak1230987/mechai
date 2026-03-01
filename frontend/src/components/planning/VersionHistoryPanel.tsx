/**
 * VersionHistoryPanel — version list with rollback + confirmation.
 */

import { useState } from "react";
import { useVersioning } from "@/hooks/useVersioning";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { History, RotateCcw, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";

export function VersionHistoryPanel() {
  const { versionHistory, currentVersion, isRollingBack, rollback } =
    useVersioning();
  const [confirmVersion, setConfirmVersion] = useState<number | null>(null);

  const handleRollback = async () => {
    if (confirmVersion == null) return;
    await rollback(confirmVersion);
    setConfirmVersion(null);
  };

  if (versionHistory.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center">
          <History className="mx-auto h-8 w-8 text-muted-foreground/30 mb-2" />
          <p className="text-sm">No version history</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <ScrollArea className="h-full">
        <div className="space-y-2 p-3">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Version History
          </h3>

          {versionHistory.map((v) => {
            const isCurrent = v.version === currentVersion;

            return (
              <div
                key={v.version}
                className={cn(
                  "rounded-md border p-2.5 transition-all",
                  isCurrent
                    ? "border-primary/40 bg-primary/5"
                    : "border-border/50 bg-transparent",
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-foreground">
                      v{v.version}
                    </span>
                    {isCurrent && (
                      <Badge variant="default" className="text-[9px] h-4">
                        Current
                      </Badge>
                    )}
                    {v.is_rollback && (
                      <Badge variant="outline" className="text-[9px] h-4">
                        Rollback
                      </Badge>
                    )}
                  </div>

                  {!isCurrent && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 text-[10px] px-2"
                      disabled={isRollingBack}
                      onClick={() => setConfirmVersion(v.version)}
                    >
                      <RotateCcw className="mr-1 h-3 w-3" />
                      Restore
                    </Button>
                  )}
                </div>

                <p className="text-[10px] text-muted-foreground/60 mt-1 ml-5">
                  {v.created_at
                    ? new Date(v.created_at).toLocaleString()
                    : "—"}
                </p>
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* Rollback confirmation */}
      <AlertDialog
        open={confirmVersion != null}
        onOpenChange={(open) => {
          if (!open) setConfirmVersion(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Rollback to v{confirmVersion}?</AlertDialogTitle>
            <AlertDialogDescription>
              This will create a new version with the plan state from v
              {confirmVersion}. The current plan will be preserved in version
              history.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleRollback} disabled={isRollingBack}>
              {isRollingBack ? "Rolling back…" : "Confirm Rollback"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}