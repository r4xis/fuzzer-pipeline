import ApiUnreachable from "./ApiUnreachable";

// "<found> · <reported> rep.", always both, so a fresh target reads "0 · 0 rep."
function countLabel(c) {
  if (!c) return "";
  return `${c.total} · ${c.reported} rep.`;
}

export default function Sidebar({ tree, treeError, counts, fleetById, onRetry, selection, onSelectProgram, onSelectTarget, open, onClose }) {
  return (
    <>
      <div className={`sidebar-backdrop ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="nav-section-label">Programs / targets</div>
        {treeError && !tree && (
          <div className="nav-notice">
            <ApiUnreachable error={treeError} onRetry={onRetry} compact />
          </div>
        )}
        {!tree && !treeError && <div className="loading nav-notice">loading…</div>}
        {tree &&
          tree.map(({ program, targets }) => (
            <div className="nav-program" key={program.id}>
              <button
                className={`nav-program-name ${selection.programId === program.id && !selection.targetId ? "active" : ""}`}
                onClick={() => onSelectProgram(program.id)}
              >
                <span>{program.name}</span>
                <span className="nav-program-count">{targets.length} target{targets.length === 1 ? "" : "s"}</span>
              </button>
              {targets.map((t) => {
                const running = Boolean(fleetById?.get(t.id)?.running);
                return (
                  <button
                    key={t.id}
                    className={`nav-target ${running ? "is-running" : ""} ${selection.targetId === t.id ? "active" : ""}`}
                    onClick={() => onSelectTarget(program.id, t.id)}
                    title={[
                      running ? "actively fuzzing" : "not running",
                      counts[t.id] ? `${counts[t.id].total} findings, ${counts[t.id].reported} reported` : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  >
                    <span className="nav-target-focus">{t.focus}</span>
                    <span className="nav-target-meta">{countLabel(counts[t.id])}</span>
                  </button>
                );
              })}
            </div>
          ))}
      </aside>
    </>
  );
}
