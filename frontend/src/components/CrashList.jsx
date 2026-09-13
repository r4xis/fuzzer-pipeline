import { useEffect, useState } from "react";
import { fetchCrashes } from "../api/client";
import { fmtDate, severityLevel } from "../format";

const TABS = [
  { key: "all", label: "All findings", status: undefined },
  { key: "reported", label: "Reported", status: "reported" },
];

// Mounted with key={targetId} by the parent, so switching target remounts it.
export default function CrashList({ targetId, refreshKey, onSelect }) {
  const [tab, setTab] = useState("all");
  const status = TABS.find((t) => t.key === tab).status;
  const identity = `${targetId}|${status || ""}`;

  // Results are tagged with the identity they belong to; a tab change reads as
  // "loading" until its own response lands, while a refreshKey bump (new crash
  // detected) re-fetches the same identity and keeps the old rows visible.
  const [state, setState] = useState({ identity: null, crashes: null, error: null });

  useEffect(() => {
    let alive = true;
    fetchCrashes(targetId, { status })
      .then((list) => alive && setState({ identity, crashes: list, error: null }))
      .catch((error) => alive && setState({ identity, crashes: null, error }));
    return () => {
      alive = false;
    };
  }, [targetId, status, identity, refreshKey]);

  const current = state.identity === identity;
  const crashes = current ? state.crashes : null;
  const error = current ? state.error : null;

  return (
    <div>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            className={`tab ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {tab === t.key && crashes && <span className="tab-count">{crashes.length}</span>}
          </button>
        ))}
      </div>

      {error && <div className="error">failed to load findings: {String(error.message || error)}</div>}
      {!crashes && !error && <div className="loading" style={{ padding: "14px 4px" }}>loading…</div>}
      {crashes && crashes.length === 0 && (
        <div className="empty-row">{tab === "reported" ? "nothing reported yet" : "no findings recorded"}</div>
      )}
      {crashes &&
        crashes.map((c) => (
          <button key={c.id} className="row-btn crash-row" onClick={() => onSelect(c.id)}>
            <span className={`sev-dot sev-${severityLevel(c.severity_type)}`} title={c.severity_type} />
            <span className="crash-line" title={c.crash_line}>{c.crash_line}</span>
            <span className={`status-pill status-${c.status}`}>{c.status}</span>
            <span className="crash-date">{fmtDate(c.discovered_at)}</span>
          </button>
        ))}
    </div>
  );
}
