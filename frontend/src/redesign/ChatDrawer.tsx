import type { CSSProperties } from "react";

const SUGGESTIONS = [
  "Why am I getting rejected?",
  "Who should I follow up with?",
  "How is my search going overall?",
];

function messageStyle(who: "user" | "ai"): CSSProperties {
  if (who === "user") {
    return {
      alignSelf: "flex-end",
      maxWidth: "85%",
      padding: "10px 14px",
      borderRadius: "14px 14px 4px 14px",
      background: "#1B201C",
      color: "#F6F4EC",
    };
  }
  return {
    alignSelf: "flex-start",
    maxWidth: "92%",
    padding: "12px 14px",
    borderRadius: "14px 14px 14px 4px",
    background: "#F4F2FB",
    border: "1px solid #E9E5F7",
    color: "#2B2833",
  };
}

export function ChatDrawer({ onClose }: { onClose: () => void }) {
  return (
    <aside
      aria-label="Ask AI drawer"
      style={{
        width: "380px",
        flex: "none",
        display: "flex",
        flexDirection: "column",
        borderLeft: "1px solid #E4E2DA",
        background: "#fff",
        animation: "rd-slide-in 0.22s ease",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 18px",
          borderBottom: "1px solid #F0EEE7",
        }}
      >
        <div>
          <div
            style={{
              fontWeight: 700,
              fontSize: "14px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span
              style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#6C5FC7" }}
            />
            Ask your job search
          </div>
          <div style={{ fontSize: "11.5px", color: "#9A9F96" }}>
            Phase 5 unavailable - grounded chat is not active
          </div>
        </div>
        <button
          aria-label="Close chat"
          onClick={onClose}
          style={{
            border: "none",
            background: "none",
            color: "#9A9F96",
            fontSize: "16px",
            cursor: "pointer",
          }}
          type="button"
        >
          ✕
        </button>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "18px",
          display: "flex",
          flexDirection: "column",
          gap: "12px",
        }}
      >
        <div style={messageStyle("ai")}>
          <div style={{ fontSize: "13px", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
            Chat arrives in Phase 5 after answers can use deterministic metrics, cited retrieval,
            and persisted local history.
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "4px" }}>
          {SUGGESTIONS.map((suggestion) => (
            <button
              className="rd-hover-lavender"
              disabled
              key={suggestion}
              style={{
                alignSelf: "flex-start",
                border: "1px dashed #D9D2EE",
                borderRadius: "999px",
                background: "#FBFAFE",
                padding: "6px 12px",
                fontSize: "12px",
                color: "#4B3FA6",
                cursor: "pointer",
                textAlign: "left",
              }}
              type="button"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>

      <div
        style={{
          padding: "14px 16px",
          borderTop: "1px solid #F0EEE7",
          display: "flex",
          gap: "8px",
        }}
      >
        <input
          disabled
          placeholder="e.g. Why am I getting rejected?"
          style={{
            flex: 1,
            padding: "10px 14px",
            border: "1px solid #E4E2DA",
            borderRadius: "10px",
            background: "#FAFAF7",
            fontSize: "13px",
            outline: "none",
          }}
        />
        <button
          disabled
          style={{
            padding: "10px 16px",
            border: "none",
            borderRadius: "10px",
            background: "#6C5FC7",
            color: "#fff",
            fontWeight: 600,
            fontSize: "13px",
            cursor: "pointer",
          }}
          type="button"
        >
          Ask
        </button>
      </div>
    </aside>
  );
}
