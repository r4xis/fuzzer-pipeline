import ApiUnreachable from "./ApiUnreachable";
import { fmtDate } from "../format";

function countsLabel(c) {
  if (c === undefined) return "…";
  if (c === null) return "—";
  return `${c.total} finding${c.total === 1 ? "" : "s"} · ${c.reported} reported`;
}

export default function IndexView({ tree, treeError, counts, onRetry, onSelectTarget }) {
  return (
    <div>
      <div className="view-header">
        <p className="eyebrow">Index</p>
        <h1 className="view-title">Fuzzing targets</h1>
        <p className="view-lead">
          Each target is one input format of the program under test, fuzzed with its own harness.
          Open a target for its coverage history, fuzzer instances and findings.
        </p>
      </div>

      {treeError && !tree && <ApiUnreachable error={treeError} onRetry={onRetry} />}
      {!tree && !treeError && <div className="loading">loading…</div>}

      {tree &&
        tree.map(({ program, targets }) => (
          <section className="index-program" key={program.id}>
            <div className="index-program-head">
              <h2 className="index-program-name">{program.name}</h2>
              {program.repo_url && (
                <a className="index-program-repo" href={program.repo_url} target="_blank" rel="noreferrer">
                  {program.repo_url.replace(/^https?:\/\//, "")}
                </a>
              )}
            </div>
            {targets.length === 0 && <div className="empty-row">no targets registered</div>}
            {targets.map((t) => (
              <button key={t.id} className="row-btn target-row" onClick={() => onSelectTarget(program.id, t.id)}>
                <span className="focus">{t.focus}</span>
                <span className="since">{t.created_at ? `since ${fmtDate(t.created_at)}` : ""}</span>
                <span className="count">{countsLabel(counts[t.id])}</span>
                <span className="arrow">→</span>
              </button>
            ))}
          </section>
        ))}
    </div>
  );
}
