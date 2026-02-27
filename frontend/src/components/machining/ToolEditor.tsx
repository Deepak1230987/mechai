import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Wrench } from "lucide-react";
import type { Tool, ToolType } from "@/types/machining";

const TOOL_TYPES: ToolType[] = [
  "DRILL",
  "FLAT_END_MILL",
  "BALL_END_MILL",
  "SLOT_CUTTER",
  "TURNING_INSERT",
];

function formatLabel(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");
}

interface ToolEditorProps {
  tool: Tool;
  onUpdate: (toolId: string, patch: Partial<Tool>) => void;
}

export function ToolEditor({ tool, onUpdate }: ToolEditorProps) {
  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          <Wrench className="size-4 text-muted-foreground" />
          {tool.id}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {/* Type */}
        <div className="col-span-2 space-y-1 sm:col-span-1">
          <Label className="text-xs">Type</Label>
          <Select
            value={tool.type}
            onValueChange={(v) => onUpdate(tool.id, { type: v as ToolType })}
          >
            <SelectTrigger size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TOOL_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {formatLabel(t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Diameter */}
        <div className="space-y-1">
          <Label className="text-xs">Diameter (mm)</Label>
          <Input
            type="number"
            step="0.1"
            min="0"
            className="h-8 text-xs"
            value={tool.diameter}
            onChange={(e) =>
              onUpdate(tool.id, { diameter: Number(e.target.value) })
            }
          />
        </div>

        {/* Max depth */}
        <div className="space-y-1">
          <Label className="text-xs">Max Depth (mm)</Label>
          <Input
            type="number"
            step="0.1"
            min="0"
            className="h-8 text-xs"
            value={tool.max_depth}
            onChange={(e) =>
              onUpdate(tool.id, { max_depth: Number(e.target.value) })
            }
          />
        </div>

        {/* RPM min */}
        <div className="space-y-1">
          <Label className="text-xs">RPM Min</Label>
          <Input
            type="number"
            step="100"
            min="0"
            className="h-8 text-xs"
            value={tool.recommended_rpm_min}
            onChange={(e) =>
              onUpdate(tool.id, {
                recommended_rpm_min: Number(e.target.value),
              })
            }
          />
        </div>

        {/* RPM Max */}
        <div className="space-y-1">
          <Label className="text-xs">RPM Max</Label>
          <Input
            type="number"
            step="100"
            min="0"
            className="h-8 text-xs"
            value={tool.recommended_rpm_max}
            onChange={(e) =>
              onUpdate(tool.id, {
                recommended_rpm_max: Number(e.target.value),
              })
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}
