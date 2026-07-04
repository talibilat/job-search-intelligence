import type { CSSProperties, ReactElement, ReactNode } from "react";
import { useId } from "react";
import { ResponsiveContainer } from "recharts";

interface ChartEmptyStateProps {
  title: string;
  description: string;
  action?: ReactNode;
}

interface ChartPanelProps {
  title: string;
  description: string;
  children?: ReactElement;
  emptyState?: ChartEmptyStateProps;
  height?: number;
}

export function ChartPanel({
  title,
  description,
  children,
  emptyState,
  height = 280,
}: ChartPanelProps) {
  const chartId = useId();
  const titleId = `${chartId}-title`;
  const descriptionId = `${chartId}-description`;
  const surfaceStyle = {
    "--chart-min-height": `${height}px`,
  } as CSSProperties;

  return (
    <section
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="chart-panel"
    >
      <div className="chart-panel__header">
        <p className="eyebrow">Recharts foundation</p>
        <h2 id={titleId}>{title}</h2>
        <p className="chart-panel__description" id={descriptionId}>
          {description}
        </p>
      </div>

      <div className="chart-panel__surface" style={surfaceStyle}>
        {children ? (
          <div
            aria-describedby={descriptionId}
            aria-labelledby={titleId}
            className="chart-panel__viewport"
            role="img"
          >
            <ResponsiveContainer height={height} width="100%">
              {children}
            </ResponsiveContainer>
          </div>
        ) : (
          <ChartEmptyState
            action={emptyState?.action}
            description={
              emptyState?.description ??
              "Connect a deterministic metrics endpoint before rendering a chart."
            }
            title={emptyState?.title ?? "No chart data yet"}
          />
        )}
      </div>
    </section>
  );
}

export function ChartEmptyState({ title, description, action }: ChartEmptyStateProps) {
  const emptyStateId = useId();
  const titleId = `${emptyStateId}-title`;
  const descriptionId = `${emptyStateId}-description`;

  return (
    <div
      aria-describedby={descriptionId}
      aria-labelledby={titleId}
      className="chart-empty-state"
      role="status"
    >
      <p className="chart-empty-state__title" id={titleId}>
        {title}
      </p>
      <p className="chart-empty-state__description" id={descriptionId}>
        {description}
      </p>
      {action ? <div className="chart-empty-state__action">{action}</div> : null}
    </div>
  );
}
