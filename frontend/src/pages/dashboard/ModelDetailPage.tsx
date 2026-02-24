import { useParams, Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { MOCK_MODELS } from "@/lib/mock-data";
import { ArrowLeft, Calendar, Eye, Hash, Layers } from "lucide-react";

export function ModelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const model = MOCK_MODELS.find((m) => m.id === id);

  if (!model) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h2 className="text-xl font-semibold mb-2">Model not found</h2>
        <p className="text-muted-foreground mb-4">
          The model you're looking for doesn't exist.
        </p>
        <Button asChild variant="outline">
          <Link to="/models">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Models
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <>
      <PageHeader title={model.name} description={`Model ID: ${model.id}`}>
        <Button asChild variant="outline">
          <Link to="/models">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Models
          </Link>
        </Button>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Model info */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Model Information</CardTitle>
            <CardDescription>
              Details and metadata for this CAD model.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex items-center gap-3">
                <Hash className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Version</p>
                  <p className="font-medium">v{model.version}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Layers className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <StatusBadge status={model.status} />
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Eye className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Visibility</p>
                  <Badge variant="outline" className="capitalize">
                    {model.visibility.toLowerCase()}
                  </Badge>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium">
                    {new Date(model.createdAt).toLocaleDateString("en-US", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                </div>
              </div>
            </div>

            <Separator />

            <div>
              <p className="text-sm text-muted-foreground mb-2">
                3D Viewer (Coming in Phase 2)
              </p>
              <div className="flex h-64 items-center justify-center rounded-lg border-2 border-dashed bg-muted/50">
                <p className="text-sm text-muted-foreground">
                  Three.js viewer will be integrated here
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Actions panel */}
        <Card>
          <CardHeader>
            <CardTitle>Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full" disabled={model.status !== "READY"}>
              Request RFQ
            </Button>
            <Button variant="outline" className="w-full">
              Download CAD File
            </Button>
            <Button variant="outline" className="w-full">
              Share Model
            </Button>
            <Separator />
            <Button variant="destructive" className="w-full">
              Delete Model
            </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
