import { useEffect, useState } from "react";
import { fetchPrograms } from "../api/client";

export default function ProgramList({ onSelect }) {
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPrograms()
      .then(setPrograms)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="muted">Loading...</p>;

  return (
    <div className="crash-list">
      {programs.map((p) => (
        <div key={p.id} className="crash-row" onClick={() => onSelect(p.id)}>
          <span className="crash-path">{p.name}</span>
          {p.repo_url && <span className="muted">{p.repo_url}</span>}
        </div>
      ))}
    </div>
  );
}
