import { useState } from "react";
import { useElementWidth } from "../hooks";
import { fmtDateTime, fmtPct } from "../format";

const HEIGHT = 200;
const M = { top: 16, right: 70, bottom: 26, left: 50 };
const SLAVE_COLORS = ["#5fa8d3", "#d19a5a", "#b48ead", "#8a9ba8", "#c47a9c", "#7a9cc4"];

function isMaster(name) {
  return name === "fuzzer0";
}

function niceStep(raw) {
  if (raw <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const m = raw / pow;
  const s = m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10;
  return s * pow;
}

function decimalsFor(step) {
  if (step >= 1) return 0;
  return Math.min(3, Math.ceil(-Math.log10(step)));
}

// Scale y to the data's own range so a 9% run reads as a real curve instead
// of a flat line pinned to the bottom of a 0-100 axis.
function computeScale(values) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const pad = span > 0 ? span * 0.3 : Math.max(0.25, Math.abs(max) * 0.1);
  let lo = Math.max(0, min - pad);
  let hi = Math.min(100, max + pad);
  if (hi - lo < 0.05) hi = lo + 0.5;

  const step = niceStep((hi - lo) / 3);
  const ticks = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) ticks.push(+t.toFixed(6));
  return { lo, hi, ticks, decimals: decimalsFor(step) };
}

// One series per fuzzer instance, master first. Falls back to the
// session-level history when no per-instance readings exist.
function buildSeries(instances, history) {
  const byName = new Map();
  for (const r of instances || []) {
    const t = new Date(r.recorded_at).getTime();
    const v = Number(r.coverage_pct);
    if (Number.isNaN(t) || Number.isNaN(v)) continue;
    if (!byName.has(r.instance_name)) byName.set(r.instance_name, []);
    byName.get(r.instance_name).push({ t, v });
  }

  if (byName.size === 0) {
    const points = (history || [])
      .map((h) => ({ t: new Date(h.recorded_at).getTime(), v: Number(h.coverage_pct) }))
      .filter((p) => !Number.isNaN(p.t) && !Number.isNaN(p.v))
      .sort((a, b) => a.t - b.t);
    return points.length ? [{ name: "session", label: "session", master: true, color: "var(--phosphor)", points }] : [];
  }

  const names = [...byName.keys()].sort((a, b) => {
    if (isMaster(a) !== isMaster(b)) return isMaster(a) ? -1 : 1;
    return a.localeCompare(b, undefined, { numeric: true });
  });

  let slaveIndex = 0;
  return names.map((name) => {
    const master = isMaster(name);
    const color = master ? "var(--phosphor)" : SLAVE_COLORS[slaveIndex++ % SLAVE_COLORS.length];
    return { name, label: name, master, color, points: byName.get(name).sort((a, b) => a.t - b.t) };
  });
}

export default function CoverageChart({ instances, history }) {
  const [ref, width] = useElementWidth();
  const [hidden, setHidden] = useState(() => new Set());

  if (instances === null && history === null) return <div className="loading">loading coverage…</div>;

  const series = buildSeries(instances, history);
  if (series.length === 0) {
    return <div className="chart-empty">no coverage readings recorded for this session yet</div>;
  }

  const toggle = (name) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const visible = series.filter((s) => !hidden.has(s.name));
  const allPoints = visible.flatMap((s) => s.points);

  const w = Math.max(width, 320);
  const innerW = w - M.left - M.right;
  const innerH = HEIGHT - M.top - M.bottom;

  let chart;
  if (allPoints.length === 0) {
    chart = <div className="chart-empty">all instances hidden — select one in the legend</div>;
  } else {
    const { lo, hi, ticks, decimals } = computeScale(allPoints.map((p) => p.v));
    const t0 = Math.min(...allPoints.map((p) => p.t));
    const t1 = Math.max(...allPoints.map((p) => p.t));
    const tSpan = Math.max(1, t1 - t0);
    const X = (t) => M.left + ((t - t0) / tSpan) * innerW;
    const Y = (v) => M.top + (1 - (v - lo) / (hi - lo)) * innerH;
    const master = visible.find((s) => s.master) || visible[0];
    const masterLast = master.points[master.points.length - 1];

    chart = (
      <svg className="chart-svg" width={w} height={HEIGHT} viewBox={`0 0 ${w} ${HEIGHT}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="tick-line" x1={M.left} x2={w - M.right} y1={Y(t)} y2={Y(t)} />
            <text x={M.left - 8} y={Y(t) + 3.5} textAnchor="end">
              {t.toFixed(decimals)}%
            </text>
          </g>
        ))}
        <line className="axis-line" x1={M.left} x2={w - M.right} y1={M.top + innerH} y2={M.top + innerH} />
        {visible.map((s) => {
          const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ");
          const last = s.points[s.points.length - 1];
          return (
            <g key={s.name}>
              {s.points.length === 1 ? (
                <circle cx={X(last.t)} cy={Y(last.v)} r={3} style={{ fill: s.color }} />
              ) : (
                <path className={s.master ? "line line-master" : "line line-slave"} d={d} style={{ stroke: s.color }} />
              )}
              <circle className="point" cx={X(last.t)} cy={Y(last.v)} r={s.master ? 3.2 : 2.4} style={{ stroke: s.color, fill: s.master ? s.color : "var(--bg)" }} />
            </g>
          );
        })}
        <text className="value-label" x={X(masterLast.t) + 9} y={Y(masterLast.v) + 4} textAnchor="start">
          {fmtPct(masterLast.v)}
        </text>
        <text x={M.left} y={HEIGHT - 8} textAnchor="start">{fmtDateTime(t0)}</text>
        <text x={w - M.right} y={HEIGHT - 8} textAnchor="end">{fmtDateTime(t1)}</text>
      </svg>
    );
  }

  return (
    <div className="chart" ref={ref}>
      {chart}
      <div className="legend" role="group" aria-label="Instances">
        {series.map((s) => {
          const last = s.points[s.points.length - 1];
          const off = hidden.has(s.name);
          return (
            <button
              key={s.name}
              className={`legend-item ${off ? "off" : ""}`}
              onClick={() => toggle(s.name)}
              aria-pressed={!off}
            >
              <span className="swatch" style={{ background: s.color }} />
              {s.master && s.name !== "session" && <span className="chip-m">M</span>}
              <span className="legend-name">{s.label}</span>
              <span className="legend-value">{fmtPct(last.v)}</span>
            </button>
          );
        })}
        <span className="chart-note">{series[0].points.length} readings per instance · y-axis scaled to this session</span>
      </div>
    </div>
  );
}
