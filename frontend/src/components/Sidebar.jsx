import ApiUnreachable from "./ApiUnreachable";

export default function Sidebar({ tree, treeError, onRetry, selection, onSelectProgram, onSelectTarget, open, onClose }) {
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
              {targets.map((t) => (
                <button
                  key={t.id}
                  className={`nav-target ${selection.targetId === t.id ? "active" : ""}`}
                  onClick={() => onSelectTarget(program.id, t.id)}
                >
                  <span className="nav-target-focus">{t.focus}</span>
                  <span className="nav-target-meta">{t.harness_version || ""}</span>
                </button>
              ))}
            </div>
          ))}
      </aside>
    </>
  );
}
