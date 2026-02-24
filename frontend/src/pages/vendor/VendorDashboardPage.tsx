import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MOCK_RFQS, MOCK_VENDORS } from "@/lib/mock-data";
import { FileText, CheckCircle, Clock, DollarSign } from "lucide-react";

export function VendorDashboardPage() {
  const { user } = useAuth();

  const vendor = MOCK_VENDORS.find((v) => v.id === user?.id) ?? MOCK_VENDORS[0];

  const stats = [
    {
      title: "Total RFQs",
      value: MOCK_RFQS.length,
      icon: FileText,
      description: "Requests received",
    },
    {
      title: "Pending",
      value: MOCK_RFQS.filter((r) => r.status === "PENDING").length,
      icon: Clock,
      description: "Awaiting your quote",
    },
    {
      title: "Quoted",
      value: MOCK_RFQS.filter((r) => r.status === "QUOTED").length,
      icon: DollarSign,
      description: "Quotes submitted",
    },
    {
      title: "Accepted",
      value: MOCK_RFQS.filter((r) => r.status === "ACCEPTED").length,
      icon: CheckCircle,
      description: "Won contracts",
    },
  ];

  return (
    <>
      <PageHeader
        title={`Welcome, ${vendor.companyName}`}
        description="Overview of your vendor activity and RFQ status."
      />

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title} className="border-border bg-card">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground/60" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-semibold tracking-tight">
                {stat.value}
              </div>
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
