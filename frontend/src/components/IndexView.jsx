import { useEffect, useState } from "react";
import { fetchCrashes } from "../api/client";
import ApiUnreachable from "./ApiUnreachable";

function TargetRow({ target, onSelect }) {
  const [counts, setCounts] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCrashes(target.id)
      .then((list) => {
        if (!alive) return;
        setCounts({
          total: list.length,
          reported: list.filter((c) => c.status === "reported").length,
        });
      })
      .catch(() => alive && setCounts({ total: null, reported: null }));
    return () => {
      alive = false;
    };
  }, [target.id]);

  return (
    <button className="row-btn target-row" onClick={onSelect}>
      <span className="focus">{target.focus}</span>
      <span className="harness">{target.harness_version || "—"}</span>
      <span className="count">
        {counts === null
          ? "…"
          : counts.total === null
            ? "—"
            : `${counts.total} finding${counts.total === 1 ? "" : "s"} · ${counts.reported} reported`}
      </span>
      <span className="arrow">→</span>
    </button>
  );
}

export default function IndexView({ tree, treeError, onRetry, onSelectTarget }) {
  return (
    <div>
      <div className="view-header">
        <p className="eyebrow">Index</p>
        <h1 className="view-title">Fuzzing targets</h1>
        <p className="view-lead">
          Each target is one input format of the library under test, fuzzed with its own
          harness. Open a target for its coverage history, fuzzer instances and findings.
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
              <TargetRow key={t.id} target={t} onSelect={() => onSelectTarget(program.id, t.id)} />
            ))}
          </section>
        ))}
    </div>
  );
}
