import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MOCK_MODELS } from "@/lib/mock-data";

export function AdminModelsPage() {
  return (
    <>
      <PageHeader
        title="All Models"
        description="View and manage all CAD models across the platform."
      />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Version</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Visibility</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_MODELS.map((model) => (
                <TableRow key={model.id}>
                  <TableCell className="font-mono text-xs">
                    {model.id}
                  </TableCell>
                  <TableCell className="font-medium">{model.name}</TableCell>
                  <TableCell>v{model.version}</TableCell>
                  <TableCell>
                    <StatusBadge status={model.status} />
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="capitalize text-xs">
                      {model.visibility.toLowerCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(model.createdAt).toLocaleDateString()}
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
