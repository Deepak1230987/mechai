import { Badge } from "@/components/ui/badge";
import { TriangleAlert } from "lucide-react";

interface MeshDensityIndicatorProps {
  triangleCount: number;
}

function getDensityLevel(count: number) {
  if (count < 50_000)
    return { label: "Low", color: "bg-emerald-500/15 text-emerald-600" };
  if (count <= 100_000)
    return { label: "Medium", color: "bg-amber-500/15 text-amber-600" };
  return { label: "High", color: "bg-red-500/15 text-red-600" };
}

export function MeshDensityIndicator({
  triangleCount,
}: MeshDensityIndicatorProps) {
  const { label, color } = getDensityLevel(triangleCount);
  const isHigh = triangleCount > 100_000;

  return (
    <div className="flex items-center gap-2">
      <Badge variant="outline" className={color}>
        {label} Density
      </Badge>
      <span className="text-xs text-muted-foreground">
        {triangleCount.toLocaleString()} triangles
      </span>
      {isHigh && (
        <Badge variant="outline" className="bg-red-500/15 text-red-600 gap-1">
          <TriangleAlert className="h-3 w-3" />
          Performance Warning
        </Badge>
      )}
    </div>
  );
}
