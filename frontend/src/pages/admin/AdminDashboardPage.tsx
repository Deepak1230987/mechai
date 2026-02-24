import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MOCK_MODELS, MOCK_VENDORS, MOCK_RFQS } from "@/lib/mock-data";
import { Users, Box, FileText, ShieldCheck } from "lucide-react";

export function AdminDashboardPage() {
  const stats = [
    {
      title: "Total Vendors",
      value: MOCK_VENDORS.length,
      icon: Users,
      description: `${MOCK_VENDORS.filter((v) => v.approved).length} approved`,
    },
    {
      title: "Total Models",
      value: MOCK_MODELS.length,
      icon: Box,
      description: `${MOCK_MODELS.filter((m) => m.status === "READY").length} ready`,
    },
    {
      title: "Total RFQs",
      value: MOCK_RFQS.length,
      icon: FileText,
      description: `${MOCK_RFQS.filter((r) => r.status === "PENDING").length} pending`,
    },
    {
      title: "Pending Approvals",
      value: MOCK_VENDORS.filter((v) => !v.approved).length,
      icon: ShieldCheck,
      description: "Vendors awaiting review",
    },
  ];

  return (
    <>
      <PageHeader
        title="Admin Dashboard"
        description="Platform overview and management tools."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {stat.description}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
