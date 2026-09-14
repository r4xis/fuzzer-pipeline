import CoverageChart from "./CoverageChart";
import InstanceTable from "./InstanceTable";
import CrashList from "./CrashList";
import SignalTrace from "./SignalTrace";
import { fmtCompact, fmtDate, fmtDateTime, fmtPct } from "../format";

// Readings outlive the fuzzers: once a run has stopped the charts keep
// showing it, so say so next to them.
function runNote(session) {
  if (session.liveState !== "closed") return null;
  if (session.endedAt) return `run stopped ${fmtDateTime(session.endedAt)}`;
  if (session.latestAt) return `run stopped · last reading ${fmtDateTime(session.latestAt)}`;
  return "run stopped";
}

export default function TargetOverview({ program, target, session, crashWatch, onSelectCrash, onBack }) {
  const latestHistory = session.history && session.history.length ? session.history[session.history.length - 1] : null;
  const total = crashWatch.count;
  const reported = crashWatch.crashes ? crashWatch.crashes.filter((c) => c.status === "reported").length : null;
  const note = runNote(session);

  return (
    <div>
      <button className="btn-link" onClick={onBack}>← {program.name}</button>

      <div className="target-head">
        <div className="view-header">
          <p className="eyebrow">
            {program.name}
            <span className="sep">/</span>
            target
            {target.created_at && (
              <>
                <span className="sep">·</span>
                fuzzing since {fmtDate(target.created_at)}
              </>
            )}
          </p>
          <h1 className="view-title mono">{target.focus}</h1>
        </div>
        {session.enabled && (
          <SignalTrace
            instances={session.instances}
            spikeKey={crashWatch.spikeKey}
            live={session.liveState === "live"}
          />
        )}
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
              <span className="label-note">per fuzzer instance{note ? ` · ${note}` : ""}</span>
            </div>
            {session.error ? (
              <div className="error">failed to load session data: {String(session.error.message || session.error)}</div>
            ) : (
              <CoverageChart instances={session.instances} history={session.history} />
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
        <div className="section-label">Findings</div>
        <CrashList key={target.id} targetId={target.id} refreshKey={crashWatch.spikeKey} onSelect={onSelectCrash} />
      </div>
    </div>
  );
}
