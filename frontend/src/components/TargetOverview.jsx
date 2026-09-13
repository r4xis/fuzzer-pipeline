import CoverageChart from "./CoverageChart";
import InstanceTable from "./InstanceTable";
import CrashList from "./CrashList";
import { fmtCompact, fmtPct } from "../format";

export default function TargetOverview({ program, target, session, crashWatch, onSelectCrash, onBack }) {
  const latestHistory = session.history && session.history.length ? session.history[session.history.length - 1] : null;
  const total = crashWatch.count;
  const reported = crashWatch.crashes ? crashWatch.crashes.filter((c) => c.status === "reported").length : null;

  return (
    <div>
      <button className="btn-link" onClick={onBack}>← {program.name}</button>
      <div className="view-header">
        <p className="eyebrow">
          {program.name}
          <span className="sep">/</span>
          target
          {target.harness_version && (
            <>
              <span className="sep">·</span>
              {target.harness_version}
            </>
          )}
        </p>
        <h1 className="view-title mono">{target.focus}</h1>
      </div>

      <div className="stat-strip">
        <div className="stat">
          <div className="stat-k">Coverage</div>
          <div className="stat-v accent">{latestHistory ? fmtPct(latestHistory.coverage_pct) : "—"}</div>
        </div>
        <div className="stat">
          <div className="stat-k">Total execs</div>
          <div className="stat-v">{latestHistory ? fmtCompact(latestHistory.total_execs) : "—"}</div>
        </div>
        <div className="stat">
          <div className="stat-k">Findings</div>
          <div className="stat-v">{total ?? "—"}</div>
        </div>
        <div className="stat">
          <div className="stat-k">Reported</div>
          <div className="stat-v">{reported ?? "—"}</div>
        </div>
      </div>

      {!session.enabled && (
        <div className="section">
          <div className="chart-empty">
            no fuzzing session is registered for this target, so coverage and instance data are unavailable
          </div>
        </div>
      )}

      {session.enabled && (
        <>
          <div className="section">
            <div className="section-label">
              Coverage over time
              <span className="label-note">session #{target.latest_session_id} · sampled every 15 min</span>
            </div>
            {session.error ? (
              <div className="error">failed to load session data: {String(session.error.message || session.error)}</div>
            ) : (
              <CoverageChart history={session.history} />
            )}
          </div>

          <div className="section">
            <div className="section-label">
              Fuzzer instances
              <span className="label-note">latest reading per instance</span>
            </div>
            {!session.error && <InstanceTable instances={session.instances} />}
          </div>
        </>
      )}

      <div className="section">
        <div className="section-label">
          Findings
          <span className="label-note">polled every 45 s</span>
        </div>
        <CrashList key={target.id} targetId={target.id} refreshKey={crashWatch.spikeKey} onSelect={onSelectCrash} />
      </div>
    </div>
  );
}
