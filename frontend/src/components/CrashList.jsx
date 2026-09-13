import { useEffect, useState } from "react";
import { fetchCrashes } from "../api/client";

const severityColor = (type) => {
  if (type === "EXPLOITABLE") return "var(--danger)";
  if (type === "PROBABLY_EXPLOITABLE") return "var(--warning)";
  return "var(--text-muted)";
};

export default function CrashList({ targetId, onSelect, onBack }) {
  const [crashes, setCrashes] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCrashes(targetId)
      .then(setCrashes)
      .finally(() => setLoading(false));
  }, [targetId]);

  return (
    <div>
      <button className="back-btn" onClick={onBack}>
        &larr; Back
      </button>
      {loading ? (
        <p className="muted">Loading...</p>
      ) : (
        <div className="crash-list">
          {crashes.map((c) => (
            <div key={c.id} className="crash-row" onClick={() => onSelect(c.id)}>
              <span
                className="severity-dot"
                style={{ background: severityColor(c.severity_type) }}
              />
              <span className="crash-path">{c.crash_line}</span>
              <span className="crash-date">
                {new Date(c.discovered_at).toLocaleDateString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
