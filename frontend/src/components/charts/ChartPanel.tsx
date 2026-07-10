import type { CSSProperties, ReactElement, ReactNode } from "react";
import { useId } from "react";
import { ResponsiveContainer } from "recharts";

import { InfoDisclosure } from "../ui";

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
  info?: ChartPanelInfo;
}

interface ChartPanelInfo {
  dataSource: string;
  dataTable: string;
  howToGenerate: string;
  howItWorks: string;
  missingData: string;
}

export function ChartPanel({
  title,
  description,
  children,
  emptyState,
  height = 280,
  info,
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
        <div className="chart-panel__heading-row">
          <div>
            <p className="eyebrow">Deterministic chart</p>
            <h2 id={titleId}>{title}</h2>
          </div>
          {info ? (
            <InfoDisclosure
              ariaLabel={`About ${title}`}
              buttonClassName="chart-panel__info-button"
              className="chart-panel__info-control"
              panelClassName="chart-panel__info"
            >
              <h3>How this chart works</h3>
              <dl>
                <div>
                  <dt>What it does</dt>
                  <dd>{info.howItWorks}</dd>
                </div>
                <div>
                  <dt>Endpoint</dt>
                  <dd>{info.dataSource}</dd>
                </div>
                <div>
                  <dt>Table</dt>
                  <dd>{info.dataTable}</dd>
                </div>
                <div>
                  <dt>How to get data</dt>
                  <dd>{info.howToGenerate}</dd>
                </div>
                <div>
                  <dt>If values are zero or missing</dt>
                  <dd>{info.missingData}</dd>
                </div>
              </dl>
            </InfoDisclosure>
          ) : null}
        </div>
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
