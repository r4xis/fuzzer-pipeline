import { fmtDate } from "../format";

function countsLabel(c) {
  if (c === undefined) return "…";
  if (c === null) return "—";
  return `${c.total} finding${c.total === 1 ? "" : "s"} · ${c.reported} reported`;
}

export default function TargetList({ program, targets, counts, onSelect, onBack }) {
  return (
    <div>
      <button className="btn-link" onClick={onBack}>← all programs</button>
      <div className="view-header">
        <p className="eyebrow">Program</p>
        <h1 className="view-title mono">{program.name}</h1>
        {program.repo_url && (
          <p className="view-lead">
            <a href={program.repo_url} target="_blank" rel="noreferrer">{program.repo_url}</a>
          </p>
        )}
      </div>
      <div className="section">
        <div className="section-label">Targets</div>
        {targets.length === 0 && <div className="empty-row">no targets registered for this program</div>}
        {targets.map((t) => (
          <button key={t.id} className="row-btn target-row" onClick={() => onSelect(t.id)}>
            <span className="focus">{t.focus}</span>
            <span className="since">{t.created_at ? `since ${fmtDate(t.created_at)}` : ""}</span>
            <span className="count">{countsLabel(counts[t.id])}</span>
            <span className="arrow">→</span>
          </button>
        ))}
      </div>
    </div>
  );
}
