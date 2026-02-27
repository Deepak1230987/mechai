import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Geometry } from "@/types";
import { Box, Ruler, Layers3, Shapes } from "lucide-react";

interface GeometrySummaryCardProps {
  geometry: Geometry;
  isSTL: boolean;
}

export function GeometrySummaryCard({
  geometry,
  isSTL,
}: GeometrySummaryCardProps) {
  const bb = geometry.bounding_box;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Ruler className="h-4 w-4 text-muted-foreground" />
          Geometry Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex items-center gap-3">
            <Box className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm text-muted-foreground">Bounding Box</p>
              <p className="font-medium text-sm">
                {bb.x_size.toFixed(1)} × {bb.y_size.toFixed(1)} ×{" "}
                {bb.z_size.toFixed(1)} mm
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Layers3 className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm text-muted-foreground">Surface Area</p>
              <p className="font-medium text-sm">
                {geometry.surface_area.toFixed(2)} mm²
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Box className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm text-muted-foreground">Volume</p>
              <p className="font-medium text-sm">
                {geometry.volume.toFixed(2)} mm³
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Shapes className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm text-muted-foreground">Faces</p>
              <div className="flex gap-1.5 flex-wrap">
                {geometry.planar_faces > 0 && (
                  <Badge
                    variant="outline"
                    className="bg-blue-500/15 text-blue-600"
                  >
                    {geometry.planar_faces} planar
                  </Badge>
                )}
                {geometry.cylindrical_faces > 0 && (
                  <Badge
                    variant="outline"
                    className="bg-violet-500/15 text-violet-600"
                  >
                    {geometry.cylindrical_faces} cylindrical
                  </Badge>
                )}
                {geometry.conical_faces > 0 && (
                  <Badge
                    variant="outline"
                    className="bg-amber-500/15 text-amber-600"
                  >
                    {geometry.conical_faces} conical
                  </Badge>
                )}
                {geometry.spherical_faces > 0 && (
                  <Badge
                    variant="outline"
                    className="bg-emerald-500/15 text-emerald-600"
                  >
                    {geometry.spherical_faces} spherical
                  </Badge>
                )}
                {isSTL && (
                  <Badge
                    variant="outline"
                    className="bg-zinc-500/15 text-zinc-500"
                  >
                    Mesh (triangulated)
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
