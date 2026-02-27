import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Info, TriangleAlert } from "lucide-react";

export function STLWarningBanner() {
  return (
    <Alert className="border-amber-500/30 bg-amber-500/5">
      <TriangleAlert className="h-4 w-4 text-amber-600" />
      <AlertTitle className="text-amber-600 font-semibold">
        STL Detected
      </AlertTitle>
      <AlertDescription className="text-sm text-muted-foreground">
        Feature recognition is unavailable for mesh-based formats. Upload a STEP
        or IGES file for full machining intelligence including feature detection
        and automated plan generation.
      </AlertDescription>
    </Alert>
  );
}

export function MeshModelInfoCard() {
  return (
    <Alert className="border-blue-500/30 bg-blue-500/5">
      <Info className="h-4 w-4 text-blue-600" />
      <AlertTitle className="text-blue-600 font-semibold">
        Mesh Model Detected
      </AlertTitle>
      <AlertDescription className="text-sm text-muted-foreground">
        This model is triangulated (STL). Deterministic feature recognition
        requires B-Rep formats such as STEP or IGES. Geometry metrics and RFQ
        quoting remain fully available.
      </AlertDescription>
    </Alert>
  );
}
