export default function TargetList({ program, targets, onSelect, onBack }) {
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
            <span className="harness">{t.harness_version || "—"}</span>
            <span className="count">{t.latest_session_id ? `session #${t.latest_session_id}` : "no session"}</span>
            <span className="arrow">→</span>
          </button>
        ))}
      </div>
    </div>
  );
}
