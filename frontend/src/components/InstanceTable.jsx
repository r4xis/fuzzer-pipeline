import { fmtCompact, fmtDateTime, fmtPct, fmtRate } from "../format";

// The endpoint returns every 15-minute reading for every instance; the
// table shows the latest reading per instance name.
function latestPerInstance(rows) {
  const byName = new Map();
  for (const r of rows) {
    const prev = byName.get(r.instance_name);
    if (!prev || new Date(r.recorded_at) > new Date(prev.recorded_at)) byName.set(r.instance_name, r);
  }
  return [...byName.values()].sort((a, b) => {
    const am = a.instance_name === "fuzzer0";
    const bm = b.instance_name === "fuzzer0";
    if (am !== bm) return am ? -1 : 1;
    return a.instance_name.localeCompare(b.instance_name, undefined, { numeric: true });
  });
}

export default function InstanceTable({ instances }) {
  if (!instances) return <div className="loading">loading instances…</div>;
  const rows = latestPerInstance(instances);
  if (rows.length === 0) {
    return <div className="chart-empty">no per-instance readings recorded for this session</div>;
  }

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Instance</th>
            <th>Role</th>
            <th className="num">Coverage</th>
            <th className="num">Execs / s</th>
            <th className="num">Crashes saved</th>
            <th className="num">Last reading</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const master = r.instance_name === "fuzzer0";
            return (
              <tr key={r.instance_name} className={master ? "is-master" : ""}>
                <td>
                  {master ? <span className="badge-master">M</span> : <span className="badge-slave" />}
                  {r.instance_name}
                </td>
                <td>
                  <span className={`role-label ${master ? "master" : ""}`}>{master ? "Master · -M" : "Slave · -S"}</span>
                </td>
                <td className="num">{fmtPct(r.coverage_pct)}</td>
                <td className="num">{fmtRate(r.execs_per_sec)}</td>
                <td className="num">{fmtCompact(r.crashes_saved)}</td>
                <td className="num dim">{fmtDateTime(r.recorded_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
