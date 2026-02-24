import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MOCK_MODELS, MOCK_RFQS } from "@/lib/mock-data";
import { Box, Upload, FileText, Activity } from "lucide-react";

export function DashboardPage() {
  const { user } = useAuth();

  const stats = [
    {
      title: "Total Models",
      value: MOCK_MODELS.length,
      icon: Box,
      description: "CAD models uploaded",
    },
    {
      title: "Processing",
      value: MOCK_MODELS.filter((m) => m.status === "PROCESSING").length,
      icon: Activity,
      description: "Currently being analyzed",
    },
    {
      title: "Ready",
      value: MOCK_MODELS.filter((m) => m.status === "READY").length,
      icon: Upload,
      description: "Ready for RFQ",
    },
    {
      title: "Active RFQs",
      value: MOCK_RFQS.filter(
        (r) => r.status === "PENDING" || r.status === "QUOTED",
      ).length,
      icon: FileText,
      description: "Awaiting response",
    },
  ];

  return (
    <>
      <PageHeader
        title={`Welcome, ${user?.name ?? "User"}`}
        description="Here's an overview of your manufacturing projects."
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
