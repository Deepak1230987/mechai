import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Layers, Pencil, Trash2, Check, X } from "lucide-react";
import { useState } from "react";
import type { Setup, Operation } from "@/types/machining";

interface SetupCardProps {
  setup: Setup;
  /** Full operations list — used to resolve human-readable labels for op IDs. */
  operations?: Operation[];
  onUpdate: (setupId: string, patch: Partial<Setup>) => void;
  onDelete: (setupId: string) => void;
}

/** Format an operation type slug into a readable label, e.g. SLOT_MILLING → Slot Milling */
function formatOpType(type: string): string {
  return type
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function SetupCard({ setup, operations, onUpdate, onDelete }: SetupCardProps) {
  const [editing, setEditing] = useState(false);
  const [draftOrientation, setDraftOrientation] = useState(setup.orientation);

  const commitEdit = () => {
    if (draftOrientation.trim()) {
      onUpdate(setup.setup_id, { orientation: draftOrientation.trim() });
    }
    setEditing(false);
  };

  const cancelEdit = () => {
    setDraftOrientation(setup.orientation);
    setEditing(false);
  };

  return (
    <Card className="transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:border-primary/20 bg-card/60 backdrop-blur-sm">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Layers className="size-3.5" />
          </div>

          {editing ? (
            <div className="flex items-center gap-1">
              <Input
                className="h-7 w-35 text-xs"
                value={draftOrientation}
                onChange={(e) => setDraftOrientation(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") cancelEdit();
                }}
                autoFocus
              />
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={commitEdit}
              >
                <Check className="size-3" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={cancelEdit}
              >
                <X className="size-3" />
              </Button>
            </div>
          ) : (
            <span className="flex items-center gap-1.5">
              {setup.orientation}
              <Button
                variant="ghost"
                size="icon"
                className="size-5 text-muted-foreground hover:text-foreground"
                onClick={() => setEditing(true)}
              >
                <Pencil className="size-3" />
              </Button>
            </span>
          )}
        </CardTitle>

        <Button
          variant="ghost"
          size="icon"
          className="size-7 text-muted-foreground hover:text-destructive"
          onClick={() => onDelete(setup.setup_id)}
        >
          <Trash2 className="size-3.5" />
        </Button>
      </CardHeader>

      <CardContent>
        <div className="flex flex-col gap-1.5">
          {setup.operations.length === 0 ? (
            <span className="text-xs text-muted-foreground">
              No operations assigned
            </span>
          ) : (
            setup.operations.map((opId, idx) => {
              const op = operations?.find((o) => o.id === opId);
              const label = op
                ? `${idx + 1}. ${formatOpType(op.type)} → ${op.tool_id}`
                : `${idx + 1}. ${opId.slice(0, 8)}…`;

              return (
                <Badge
                  key={opId}
                  variant="outline"
                  className="justify-start gap-1 text-xs font-normal"
                  title={opId}
                >
                  {label}
                </Badge>
              );
            })
          )}
        </div>
      </CardContent>
    </Card>
  );
}
