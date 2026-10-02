import { useRef } from "react";
import ApiUnreachable from "./ApiUnreachable";

// "<found> · <public> pub.", always both, so a fresh target reads "0 · 0 pub."
function countLabel(c) {
  if (!c) return "";
  return `${c.total} · ${c.public} pub.`;
}

// Swipe-left-to-close on touch devices. Tracked as a plain ref (not state) so
// the gesture adds no re-renders; only closes once a touch moves left past
// the threshold AND more horizontally than vertically, so swiping vertically
// to scroll the drawer's own content is never mistaken for a close gesture.
const SWIPE_CLOSE_PX = 50;

function useSwipeToClose(onClose) {
  const start = useRef(null);
  const onTouchStart = (e) => {
    const t = e.touches[0];
    start.current = { x: t.clientX, y: t.clientY };
  };
  const onTouchMove = (e) => {
    if (!start.current) return;
    const t = e.touches[0];
    const dx = t.clientX - start.current.x;
    const dy = t.clientY - start.current.y;
    if (dx <= -SWIPE_CLOSE_PX && Math.abs(dx) > Math.abs(dy)) {
      start.current = null;
      onClose();
    }
  };
  const onTouchEnd = () => {
    start.current = null;
  };
  return { onTouchStart, onTouchMove, onTouchEnd };
}

export default function Sidebar({ tree, treeError, counts, fleetById, onRetry, selection, onSelectProgram, onSelectTarget, open, onClose }) {
  const swipe = useSwipeToClose(onClose);
  return (
    <>
      <div className={`sidebar-backdrop ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`sidebar ${open ? "open" : ""}`} {...swipe}>
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
                      counts[t.id] ? `${counts[t.id].total} findings, ${counts[t.id].public} public` : null,
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
