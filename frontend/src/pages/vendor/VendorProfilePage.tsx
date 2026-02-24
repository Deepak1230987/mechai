import { useState, type FormEvent } from "react";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MOCK_VENDORS } from "@/lib/mock-data";
import { Save, Loader2 } from "lucide-react";

export function VendorProfilePage() {
  const vendor = MOCK_VENDORS[0]; // Mock: use first vendor

  const [companyName, setCompanyName] = useState(vendor.companyName);
  const [machines, setMachines] = useState(vendor.machines.join(", "));
  const [materials, setMaterials] = useState(vendor.materials.join(", "));
  const [maxPartSize, setMaxPartSize] = useState(vendor.maxPartSize);
  const [tolerance, setTolerance] = useState(vendor.toleranceCapability);
  const [isSaving, setIsSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setSaved(false);

    // Simulate save
    await new Promise((resolve) => setTimeout(resolve, 800));

    setIsSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <>
      <PageHeader
        title="Vendor Profile"
        description="Manage your company information and capabilities."
      >
        <Badge variant={vendor.approved ? "default" : "secondary"}>
          {vendor.approved ? "Approved" : "Pending Approval"}
        </Badge>
      </PageHeader>

      <Card className="max-w-2xl border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base font-semibold">Company Information</CardTitle>
          <CardDescription>
            Update your manufacturing capabilities to receive relevant RFQs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="company-name" className="text-sm font-medium">Company Name</Label>
              <Input
                id="company-name"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                required
                className="bg-input border-border"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="machines" className="text-sm font-medium">
                Machines{" "}
                <span className="text-muted-foreground text-xs">
                  (comma-separated)
                </span>
              </Label>
              <Textarea
                id="machines"
                value={machines}
                onChange={(e) => setMachines(e.target.value)}
                placeholder="3-Axis CNC, 5-Axis CNC, CNC Lathe"
                rows={2}
                className="bg-input border-border"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="materials" className="text-sm font-medium">
                Materials Supported{" "}
                <span className="text-muted-foreground text-xs">
                  (comma-separated)
                </span>
              </Label>
              <Textarea
                id="materials"
                value={materials}
                onChange={(e) => setMaterials(e.target.value)}
                placeholder="Aluminum 6061, Steel 304, Titanium"
                rows={2}
                className="bg-input border-border"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="max-part-size" className="text-sm font-medium">Max Part Size</Label>
                <Input
                  id="max-part-size"
                  value={maxPartSize}
                  onChange={(e) => setMaxPartSize(e.target.value)}
                  placeholder="500x500x300 mm"
                  className="bg-input border-border"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="tolerance" className="text-sm font-medium">Tolerance Capability</Label>
                <Input
                  id="tolerance"
                  value={tolerance}
                  onChange={(e) => setTolerance(e.target.value)}
                  placeholder="±0.01 mm"
                  className="bg-input border-border"
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Button type="submit" disabled={isSaving}>
                {isSaving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Save className="mr-2 h-4 w-4" />
                )}
                Save Profile
              </Button>
              {saved && (
                <span className="text-sm text-emerald-400">
                  Profile saved successfully!
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </>
  );
}
