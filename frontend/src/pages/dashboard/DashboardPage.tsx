import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { PageHeader } from "@/components/shared/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listModels } from "@/lib/models-api";
import type { Model } from "@/types";
import { Box, Upload, Activity, Loader2 } from "lucide-react";

export function DashboardPage() {
  const { user } = useAuth();
  const [models, setModels] = useState<Model[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    listModels()
      .then((res) => setModels(res.models))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, []);

  const stats = [
    {
      title: "Total Models",
      value: models.length,
      icon: Box,
      description: "CAD models uploaded",
    },
    {
      title: "Processing",
      value: models.filter((m) => m.status === "PROCESSING").length,
      icon: Activity,
      description: "Currently being analyzed",
    },
    {
      title: "Ready",
      value: models.filter((m) => m.status === "READY").length,
      icon: Upload,
      description: "Ready for RFQ",
    },
  ];

  return (
    <>
      <PageHeader
        title={`Welcome, ${user?.name ?? "User"}`}
        description="Here's an overview of your manufacturing projects."
      />

      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
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
      )}
    </>
  );
}
