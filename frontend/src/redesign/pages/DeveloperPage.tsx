import {
  featureStatusLabels,
  featureStatusRegistry,
} from "../../featureStatus/featureStatusRegistry";

const DEV_FEATURES = [
  { id: "backend-manual-sync-api", name: "Gmail sync", api: "POST /sync" },
  {
    id: "backend-classification-control-api",
    name: "Email classification",
    api: "GET /classification/estimate",
  },
  {
    id: "backend-application-read-api",
    name: "Applications & timeline",
    api: "GET /applications/{id}",
  },
  {
    id: "backend-application-manual-corrections-api",
    name: "Manual corrections",
    api: "POST /applications/{id}/split",
  },
  {
    id: "frontend-insights-shell",
    name: "Cached insights",
    api: "GET /insights",
  },
  {
    id: "frontend-chat-ui",
    name: "Chat agent (RAG)",
    api: "POST /chat",
    phase: "Phase 5",
  },
] as const;

const DEV_ROWS = DEV_FEATURES.map((row) => {
  const record = featureStatusRegistry.find((feature) => feature.id === row.id);
  return {
    ...row,
    phase: "phase" in row ? row.phase : null,
    status: record ? featureStatusLabels[record.status] : "Status unavailable",
    wiredTo: record && record.screens.length > 0 ? record.screens.join(", ") : null,
  };
});

export function DeveloperPage() {
  return (
    <section
      style={{
        maxWidth: "720px",
        margin: "0 auto",
        padding: "28px 32px 60px",
        display: "flex",
        flexDirection: "column",
        gap: "14px",
      }}
    >
      <div>
        <h1
          style={{
            margin: 0,
            fontSize: "22px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
          }}
        >
          For developers
        </h1>
        <p style={{ margin: "6px 0 0", color: "#666D66", fontSize: "13.5px" }}>
          Implementation status of each surface. The "Wired to" line shows where it's actually
          surfaced in the product. Not shown to regular users.
        </p>
      </div>
      <div
        style={{
          border: "1px solid #E4E2DA",
          borderRadius: "14px",
          background: "#fff",
          overflow: "hidden",
        }}
      >
        {DEV_ROWS.map((row) => (
          <div
            key={row.name}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
              padding: "12px 18px",
              borderBottom: "1px solid #F0EEE7",
              fontSize: "13px",
            }}
          >
            <span>
              <span style={{ display: "block", fontWeight: 600 }}>{row.name}</span>
              <span style={{ display: "block", fontSize: "11px", color: "#9A9F96", marginTop: "1px" }}>
                {row.wiredTo ? `Wired to ${row.wiredTo}` : "Not wired to a screen yet"}
              </span>
            </span>
            <span
              style={{ display: "flex", alignItems: "center", gap: "10px" }}
            >
              {row.phase ? (
                <span style={{ fontSize: "12px", color: "#9A9F96" }}>
                  {row.phase}
                </span>
              ) : null}
              <span
                style={{
                  fontSize: "12px",
                  color: "#9A9F96",
                  fontFamily: "'JetBrains Mono',monospace",
                }}
              >
                {row.api}
              </span>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "3px 10px",
                  borderRadius: "999px",
                  background:
                    row.status === "Completed" ? "#E3EFE6" : "#EFEFEC",
                  color: row.status === "Completed" ? "#1E5136" : "#6B7268",
                }}
              >
                {row.status}
              </span>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
