import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Layers, Pencil, Trash2, Check, X } from "lucide-react";
import { useState } from "react";
import type { Setup } from "@/types/machining";

interface SetupCardProps {
  setup: Setup;
  onUpdate: (setupId: string, patch: Partial<Setup>) => void;
  onDelete: (setupId: string) => void;
}

export function SetupCard({ setup, onUpdate, onDelete }: SetupCardProps) {
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
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Layers className="size-4 text-muted-foreground" />

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
        <div className="flex flex-wrap gap-1.5">
          {setup.operations.length === 0 ? (
            <span className="text-xs text-muted-foreground">
              No operations assigned
            </span>
          ) : (
            setup.operations.map((opId) => (
              <Badge key={opId} variant="outline" className="font-mono text-xs">
                {opId}
              </Badge>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
