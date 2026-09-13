import { useElementWidth } from "../hooks";
import { fmtDateTime, fmtPct } from "../format";

const HEIGHT = 180;
const M = { top: 14, right: 16, bottom: 26, left: 50 };

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

// Scale y to the session's own data range so a 9% run reads as a real
// curve instead of a flat line pinned to the bottom of a 0-100 axis.
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

export default function CoverageChart({ history }) {
  const [ref, width] = useElementWidth();

  if (!history) return <div className="loading">loading coverage…</div>;

  const points = history
    .map((h) => ({ t: new Date(h.recorded_at).getTime(), v: Number(h.coverage_pct) }))
    .filter((p) => !Number.isNaN(p.t) && !Number.isNaN(p.v))
    .sort((a, b) => a.t - b.t);

  if (points.length === 0) {
    return <div className="chart-empty">no coverage readings recorded for this session yet</div>;
  }

  const last = points[points.length - 1];

  if (points.length === 1) {
    return (
      <div className="chart-single">
        <span className="big">{fmtPct(last.v)}</span>
        <span className="chart-note">single reading · {fmtDateTime(history[0].recorded_at)}</span>
      </div>
    );
  }

  const { lo, hi, ticks, decimals } = computeScale(points.map((p) => p.v));
  const w = Math.max(width, 320);
  const innerW = w - M.left - M.right;
  const innerH = HEIGHT - M.top - M.bottom;
  const t0 = points[0].t;
  const t1 = last.t;
  const tSpan = Math.max(1, t1 - t0);

  const X = (t) => M.left + ((t - t0) / tSpan) * innerW;
  const Y = (v) => M.top + (1 - (v - lo) / (hi - lo)) * innerH;

  const linePath = points.map((p, i) => `${i ? "L" : "M"}${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${X(t1).toFixed(1)},${(M.top + innerH).toFixed(1)} L${X(t0).toFixed(1)},${(M.top + innerH).toFixed(1)} Z`;

  const first = points[0];
  const delta = last.v - first.v;

  return (
    <div className="chart" ref={ref}>
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
        <path className="area" d={areaPath} />
        <path className="line" d={linePath} />
        {points.map((p, i) => (
          <circle
            key={p.t}
            className={i === points.length - 1 ? "point point-last" : "point"}
            cx={X(p.t)}
            cy={Y(p.v)}
            r={i === points.length - 1 ? 3.2 : 2}
          />
        ))}
        <text
          className="value-label"
          x={Math.min(X(t1) + 8, w - M.right - 44)}
          y={Y(last.v) - 8}
          textAnchor={X(t1) + 8 > w - M.right - 44 ? "end" : "start"}
        >
          {fmtPct(last.v)}
        </text>
        <text x={M.left} y={HEIGHT - 8} textAnchor="start">{fmtDateTime(first.t)}</text>
        <text x={w - M.right} y={HEIGHT - 8} textAnchor="end">{fmtDateTime(last.t)}</text>
      </svg>
      <div className="chart-note">
        {points.length} readings · range {fmtPct(first.v)} → {fmtPct(last.v)}
        {delta !== 0 ? ` (${delta > 0 ? "+" : ""}${delta.toFixed(2)} pts)` : " (flat)"} · y-axis scaled to this session
      </div>
    </div>
  );
}
