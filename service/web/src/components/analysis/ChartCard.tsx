import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { Card, CardHeader } from "../ui/Card";

/**
 * Recharts-friendly chart wrapper matching the console's card design system.
 * Children are expected to be a Recharts chart wrapped in a ResponsiveContainer
 * so it fills the card's content area.
 */
export function ChartCard({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("overflow-hidden", className)}>
      <CardHeader title={title} description={description} />
      <div className="px-5 py-4 min-h-[260px]">{children}</div>
    </Card>
  );
}
