import { useEffect, useRef, useState } from "react";
import { useMediaQuery } from "../hooks";
import { fmtCompact } from "../format";

const W = 960;
const H = 56;
const N = 160;
const MID = H / 2;
const DATA_AMP = H * 0.34;

function isMaster(name) {
  return name === "fuzzer0";
}

function instanceNames(rows) {
  const names = [...new Set(rows.map((r) => r.instance_name))];
  return names.sort((a, b) => {
    if (isMaster(a) !== isMaster(b)) return isMaster(a) ? -1 : 1;
    return a.localeCompare(b, undefined, { numeric: true });
  });
}

function seriesFor(rows, name) {
  return rows
    .filter((r) => r.instance_name === name)
    .sort((a, b) => new Date(a.recorded_at) - new Date(b.recorded_at))
    .map((r) => Number(r.crashes_saved) || 0);
}

// Resample the reading series onto N points and normalise it to -1..1 so the
// trace shape is the instance's crashes-saved history, whatever its scale.
function normalisedShape(series) {
  if (!series || series.length < 2) return null;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min;
  const shape = new Array(N);
  for (let i = 0; i < N; i++) {
    const pos = (i / (N - 1)) * (series.length - 1);
    const lo = Math.floor(pos);
    const hi = Math.min(series.length - 1, lo + 1);
    const t = pos - lo;
    const v = series[lo] * (1 - t) + series[hi] * t;
    shape[i] = span > 0 ? ((v - min) / span) * 2 - 1 : 0;
  }
  return shape;
}

function buildPath(shape, amp, phase, spikeAge) {
  const pts = [];
  const spikeCenter = Math.round(N * 0.62);
  const spikeEnv = spikeAge === null ? 0 : Math.exp(-spikeAge / 420);

  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * W;
    let y;
    if (shape) {
      const ripple = Math.sin(phase * 1.6 + i * 0.35) * 1.2;
      y = MID - shape[i] * DATA_AMP + ripple;
    } else {
      const base = Math.sin(phase + i * 0.21) * 0.6 + Math.sin(phase * 0.63 + i * 0.077) * 0.4;
      y = MID + base * amp;
    }
    if (spikeEnv > 0.01) {
      const d = i - spikeCenter;
      const lobe = Math.exp(-(d * d) / 9) * Math.sin(d * 1.05 + 1.2);
      y += lobe * H * 0.52 * spikeEnv;
    }
    pts.push(`${x.toFixed(1)},${y.toFixed(2)}`);
  }
  return `M${pts.join(" L")}`;
}

export default function SignalTrace({ instances, spikeKey, live }) {
  const pathRef = useRef(null);
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");
  const spikeStart = useRef(null);
  const lastSpikeKey = useRef(spikeKey);
  const [selected, setSelected] = useState(null);

  const rows = instances || [];
  const names = instanceNames(rows);
  const active = names.includes(selected) ? selected : names[0] || null;
  const series = active ? seriesFor(rows, active) : null;
  const hasShape = Boolean(series && series.length >= 2);
  // Stable string key so the animation effect restarts only when readings change.
  const seriesKey = series ? series.join(",") : "";

  // The spike flash and the path geometry are written to the DOM directly
  // (the rAF loop owns the `d` attribute), so new readings or crashes never
  // force a React re-render just to move the line.
  useEffect(() => {
    const el = pathRef.current;
    if (!el || spikeKey === lastSpikeKey.current) return undefined;
    lastSpikeKey.current = spikeKey;
    spikeStart.current = performance.now();
    el.dataset.spiking = "1";
    const t = setTimeout(() => {
      delete el.dataset.spiking;
    }, 1100);
    return () => clearTimeout(t);
  }, [spikeKey]);

  useEffect(() => {
    const el = pathRef.current;
    if (!el) return undefined;

    const shape = normalisedShape(seriesKey ? seriesKey.split(",").map(Number) : null);

    if (reduceMotion) {
      el.setAttribute("d", buildPath(shape, live ? 6 : 1, 0.8, null));
      return undefined;
    }

    let raf = 0;
    let amp = live ? 7 : 1.2;
    let phase = 0;
    let last = null;

    const frame = (now) => {
      const dt = last === null ? 16 : Math.min(64, now - last);
      last = now;
      const targetAmp = live ? 7 : 1.2;
      amp += (targetAmp - amp) * 0.04;
      phase += dt * (live ? 0.0026 : 0.0011);

      let age = null;
      if (spikeStart.current !== null) {
        age = now - spikeStart.current;
        if (age > 3000) {
          spikeStart.current = null;
          age = null;
        }
      }
      el.setAttribute("d", buildPath(shape, amp, phase, age));
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [live, reduceMotion, seriesKey]);

  const latest = series && series.length ? series[series.length - 1] : null;
  const svgClass = ["signal-trace", live ? "is-live" : "", hasShape ? "has-data" : ""].filter(Boolean).join(" ");

  return (
    <div className="trace-strip">
      {names.length > 0 && (
        <div className="trace-bar">
          <div className="trace-chips" role="tablist" aria-label="Fuzzer instance">
            {names.map((name) => (
              <button
                key={name}
                role="tab"
                aria-selected={name === active}
                className={`chip ${name === active ? "active" : ""}`}
                onClick={() => setSelected(name)}
              >
                {isMaster(name) && <span className="chip-m">M</span>}
                {name}
              </button>
            ))}
          </div>
          <div className="trace-meta">
            crashes saved · {active}
            {latest !== null && <span className="trace-value">{fmtCompact(latest)}</span>}
            {series && series.length > 0 && <span className="faint"> · {series.length} readings</span>}
          </div>
        </div>
      )}
      <svg
        className={svgClass}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={
          hasShape
            ? `crashes saved over time for ${active}`
            : live
              ? "signal trace: fuzzer live"
              : "signal trace: no live signal"
        }
      >
        <line className="trace-baseline" x1="0" y1={MID} x2={W} y2={MID} />
        <path ref={pathRef} d={`M0,${MID} L${W},${MID}`} />
      </svg>
    </div>
  );
}
