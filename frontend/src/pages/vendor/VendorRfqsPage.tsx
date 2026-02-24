import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MOCK_RFQS } from "@/lib/mock-data";
import { Send } from "lucide-react";

export function VendorRfqsPage() {
  return (
    <>
      <PageHeader
        title="RFQ Requests"
        description="Review and submit quotes for incoming requests."
      />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>RFQ ID</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Quantity</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Due Date</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MOCK_RFQS.map((rfq) => (
                <TableRow key={rfq.id}>
                  <TableCell className="font-mono text-xs">
                    {rfq.id.toUpperCase()}
                  </TableCell>
                  <TableCell className="font-medium">{rfq.modelName}</TableCell>
                  <TableCell>{rfq.quantity} pcs</TableCell>
                  <TableCell>
                    <StatusBadge status={rfq.status} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(rfq.dueDate).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={rfq.status !== "PENDING"}
                    >
                      <Send className="mr-1 h-4 w-4" />
                      Submit Quote
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
