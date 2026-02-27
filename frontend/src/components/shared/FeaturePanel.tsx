import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Feature } from "@/types";
import { Shapes } from "lucide-react";

interface FeaturePanelProps {
  features: Feature[];
}

function featureColor(type: string) {
  switch (type.toUpperCase()) {
    case "HOLE":
      return "bg-blue-500/15 text-blue-600";
    case "POCKET":
      return "bg-emerald-500/15 text-emerald-600";
    case "SLOT":
      return "bg-amber-500/15 text-amber-600";
    case "BOSS":
      return "bg-violet-500/15 text-violet-600";
    default:
      return "bg-zinc-500/15 text-zinc-500";
  }
}

export function FeaturePanel({ features }: FeaturePanelProps) {
  if (features.length === 0) return null;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Shapes className="h-4 w-4 text-muted-foreground" />
          Detected Features
          <Badge variant="secondary" className="ml-auto">
            {features.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {features.map((f, i) => (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg border border-border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <Badge variant="outline" className={featureColor(f.type)}>
                  {f.type}
                </Badge>
                {f.diameter != null && (
                  <span className="text-xs text-muted-foreground">
                    ⌀{f.diameter.toFixed(2)}
                  </span>
                )}
                {f.depth != null && (
                  <span className="text-xs text-muted-foreground">
                    depth: {f.depth.toFixed(2)}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {Object.entries(f.dimensions).map(([key, val]) => (
                  <span key={key} className="text-xs text-muted-foreground">
                    {key}: {val.toFixed(2)}
                  </span>
                ))}
                <Badge variant="outline" className="text-xs">
                  {(f.confidence * 100).toFixed(0)}%
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
