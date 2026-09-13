import { useEffect, useState } from "react";
import { fetchTargets } from "../api/client";

export default function TargetList({ programId, onSelect, onBack }) {
  const [targets, setTargets] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTargets(programId)
      .then(setTargets)
      .finally(() => setLoading(false));
  }, [programId]);

  return (
    <div>
      <button className="back-btn" onClick={onBack}>
        &larr; Back
      </button>
      {loading ? (
        <p className="muted">Loading...</p>
      ) : (
        <div className="crash-list">
          {targets.map((t) => (
            <div
              key={t.id}
              className="crash-row"
              onClick={() => onSelect(t.id)}
            >
              <span className="crash-target">{t.focus}</span>
              <span className="muted">{t.harness_version}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
