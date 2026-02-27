import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Operation, OperationType } from "@/types/machining";

const OPERATION_TYPES: OperationType[] = [
  "DRILLING",
  "POCKET_ROUGHING",
  "POCKET_FINISHING",
  "SLOT_MILLING",
  "ROUGH_TURNING",
  "FINISH_TURNING",
  "FACE_MILLING",
];

function formatLabel(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");
}

interface OperationRowProps {
  operation: Operation;
  index: number;
  toolIds: string[];
  onUpdate: (id: string, patch: Partial<Operation>) => void;
  onDelete: (id: string) => void;
}

export function OperationRow({
  operation,
  index,
  toolIds,
  onUpdate,
  onDelete,
}: OperationRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: operation.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="group flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm hover:bg-muted/50"
    >
      {/* Drag handle */}
      <button
        type="button"
        className="cursor-grab text-muted-foreground hover:text-foreground active:cursor-grabbing"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>

      {/* Index */}
      <span className="w-6 shrink-0 text-center font-mono text-xs text-muted-foreground">
        {index + 1}
      </span>

      {/* Operation type */}
      <Select
        value={operation.type}
        onValueChange={(v) =>
          onUpdate(operation.id, { type: v as OperationType })
        }
      >
        <SelectTrigger size="sm" className="w-37.5">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {OPERATION_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {formatLabel(t)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Tool selector */}
      <Select
        value={operation.tool_id}
        onValueChange={(v) => onUpdate(operation.id, { tool_id: v })}
      >
        <SelectTrigger size="sm" className="w-30">
          <SelectValue placeholder="Tool" />
        </SelectTrigger>
        <SelectContent>
          {toolIds.map((tid) => (
            <SelectItem key={tid} value={tid}>
              {tid}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Feed rate */}
      <div className="flex items-center gap-1">
        <label className="text-xs text-muted-foreground">Feed</label>
        <Input
          type="number"
          className="h-7 w-17.5 text-xs"
          value={operation.parameters.feed_rate ?? ""}
          onChange={(e) =>
            onUpdate(operation.id, {
              parameters: {
                ...operation.parameters,
                feed_rate: e.target.value ? Number(e.target.value) : undefined,
              },
            })
          }
        />
      </div>

      {/* Spindle speed */}
      <div className="flex items-center gap-1">
        <label className="text-xs text-muted-foreground">RPM</label>
        <Input
          type="number"
          className="h-7 w-17.5 text-xs"
          value={operation.parameters.spindle_speed ?? ""}
          onChange={(e) =>
            onUpdate(operation.id, {
              parameters: {
                ...operation.parameters,
                spindle_speed: e.target.value
                  ? Number(e.target.value)
                  : undefined,
              },
            })
          }
        />
      </div>

      {/* Estimated time */}
      <span className="ml-auto shrink-0 text-xs text-muted-foreground">
        {operation.estimated_time.toFixed(1)}s
      </span>

      {/* Delete */}
      <Button
        variant="ghost"
        size="icon"
        className="size-7 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
        onClick={() => onDelete(operation.id)}
      >
        <Trash2 className="size-3.5" />
      </Button>
    </div>
  );
}
