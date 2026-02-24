import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { listModels } from "@/lib/models-api";
import type { Model } from "@/types";
import { Plus, Eye, Loader2, AlertCircle } from "lucide-react";

export function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setIsLoading(true);
    listModels()
      .then((res) => {
        setModels(res.models);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load models");
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <>
      <PageHeader title="Models" description="Manage your uploaded CAD models.">
        <Button asChild>
          <Link to="/models/upload">
            <Plus className="mr-2 h-4 w-4" />
            Upload Model
          </Link>
        </Button>
      </PageHeader>

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-md bg-destructive/10 p-4 text-destructive">
          <AlertCircle className="h-4 w-4" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      <Card className="border-border bg-card">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">
                Loading models...
              </span>
            </div>
          ) : models.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <p className="text-sm text-muted-foreground mb-4">
                No models yet. Upload your first CAD file to get started.
              </p>
              <Button asChild variant="outline">
                <Link to="/models/upload">
                  <Plus className="mr-2 h-4 w-4" />
                  Upload Model
                </Link>
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Format</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Visibility</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {models.map((model) => (
                  <TableRow key={model.id}>
                    <TableCell className="font-medium">{model.name}</TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="text-xs">
                        {model.file_format}
                      </Badge>
                    </TableCell>
                    <TableCell>v{model.version}</TableCell>
                    <TableCell>
                      <StatusBadge status={model.status} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs capitalize">
                        {model.visibility.toLowerCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(model.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" asChild>
                        <Link to={`/models/${model.id}`}>
                          <Eye className="mr-1 h-4 w-4" />
                          View
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  );
}
