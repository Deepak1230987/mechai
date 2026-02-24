import { useState } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
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
import { MOCK_VENDORS } from "@/lib/mock-data";
import type { VendorProfile } from "@/types";
import { CheckCircle, XCircle } from "lucide-react";

export function AdminVendorsPage() {
  const [vendors, setVendors] = useState<VendorProfile[]>(MOCK_VENDORS);

  const toggleApproval = (vendorId: string) => {
    setVendors((prev) =>
      prev.map((v) =>
        v.id === vendorId ? { ...v, approved: !v.approved } : v,
      ),
    );
  };

  return (
    <>
      <PageHeader
        title="Vendor Management"
        description="Review and approve vendor registrations."
      />

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company</TableHead>
                <TableHead>Machines</TableHead>
                <TableHead>Materials</TableHead>
                <TableHead>Max Size</TableHead>
                <TableHead>Tolerance</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vendors.map((vendor) => (
                <TableRow key={vendor.id}>
                  <TableCell className="font-medium">
                    {vendor.companyName}
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {vendor.machines.slice(0, 2).map((m) => (
                        <Badge key={m} variant="outline" className="text-xs">
                          {m}
                        </Badge>
                      ))}
                      {vendor.machines.length > 2 && (
                        <Badge variant="outline" className="text-xs">
                          +{vendor.machines.length - 2}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {vendor.materials.slice(0, 2).map((m) => (
                        <Badge key={m} variant="secondary" className="text-xs">
                          {m}
                        </Badge>
                      ))}
                      {vendor.materials.length > 2 && (
                        <Badge variant="secondary" className="text-xs">
                          +{vendor.materials.length - 2}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">
                    {vendor.maxPartSize}
                  </TableCell>
                  <TableCell className="text-sm">
                    {vendor.toleranceCapability}
                  </TableCell>
                  <TableCell>
                    <Badge variant={vendor.approved ? "default" : "secondary"}>
                      {vendor.approved ? "Approved" : "Pending"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant={vendor.approved ? "destructive" : "default"}
                      size="sm"
                      onClick={() => toggleApproval(vendor.id)}
                    >
                      {vendor.approved ? (
                        <>
                          <XCircle className="mr-1 h-4 w-4" />
                          Revoke
                        </>
                      ) : (
                        <>
                          <CheckCircle className="mr-1 h-4 w-4" />
                          Approve
                        </>
                      )}
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
