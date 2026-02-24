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
import { MOCK_MODELS } from "@/lib/mock-data";
import { Plus, Eye } from "lucide-react";

export function ModelsPage() {
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

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Visibility</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_MODELS.map((model) => (
                <TableRow key={model.id}>
                  <TableCell className="font-medium">{model.name}</TableCell>
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
                    {new Date(model.createdAt).toLocaleDateString()}
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
        </CardContent>
      </Card>
    </>
  );
}
