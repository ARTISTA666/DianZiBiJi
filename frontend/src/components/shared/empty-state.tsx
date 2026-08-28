import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description?: string;
  /** 可选操作按钮等，渲染在文案下方。 */
  action?: ReactNode;
  className?: string;
}

/**
 * 统一的虚线卡片空状态，吸收项目列表页的既有样式。
 */
export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <Card className={cn("border-dashed border-border/80 bg-card/40 backdrop-blur-sm", className)}>
      <CardContent className="flex flex-col items-center justify-center py-12 px-4 text-center">
        {Icon && (
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground ring-8 ring-muted/20">
            <Icon className="h-7 w-7 text-muted-foreground/80" />
          </div>
        )}
        <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
        {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground leading-relaxed">{description}</p>}
        {action && <div className="mt-5">{action}</div>}
      </CardContent>
    </Card>
  );
}
