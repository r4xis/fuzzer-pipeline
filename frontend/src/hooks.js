import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fetchAllTargets, fetchCrashes, fetchSessionHistory, fetchSessionInstances } from "./api/client";

const LIVE_WINDOW_MS = 20 * 60 * 1000;
const SESSION_POLL_MS = 5 * 60 * 1000;
const CRASH_POLL_MS = 45 * 1000;

// Fetch now and every `intervalMs`. Results are tagged with the identity they
// were fetched for, so a change of identity reads as "loading" without any
// synchronous reset; late responses for an old identity are ignored.
export function usePolled(fetcher, identity, intervalMs, { enabled = true, onData } = {}) {
  const key = enabled ? JSON.stringify(identity) : null;
  const [state, setState] = useState({ key: null, data: null, error: null, fetchedAt: null });
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((t) => t + 1), []);

  const latest = useRef({ fetcher, onData });
  useEffect(() => {
    latest.current = { fetcher, onData };
  });

  useEffect(() => {
    if (key === null) return undefined;
    let alive = true;

    const run = () =>
      latest.current
        .fetcher()
        .then((data) => {
          if (!alive) return;
          setState({ key, data, error: null, fetchedAt: Date.now() });
          if (latest.current.onData) latest.current.onData(data);
        })
        .catch((error) => {
          if (!alive) return;
          setState((s) => ({ key, data: s.key === key ? s.data : null, error, fetchedAt: Date.now() }));
        });

    run();
    const id = intervalMs ? setInterval(run, intervalMs) : null;
    return () => {
      alive = false;
      if (id) clearInterval(id);
    };
  }, [key, tick, intervalMs]);

  const current = key !== null && state.key === key;
  return {
    data: current ? state.data : null,
    error: current ? state.error : null,
    fetchedAt: current ? state.fetchedAt : null,
    loading: key !== null && !current,
    refresh,
  };
}

function latestTimestamp(history, instances) {
  let max = 0;
  for (const h of history || []) max = Math.max(max, new Date(h.recorded_at).getTime() || 0);
  for (const i of instances || []) max = Math.max(max, new Date(i.recorded_at).getTime() || 0);
  return max || null;
}

// `run` is the target's entry from useFleetLive (the API's view of whether
// its latest session is running). Until that has loaded, the state is
// inferred from the readings themselves.
export function useSessionData(sessionId, run = null) {
  const enabled = sessionId !== null && sessionId !== undefined;
  const history = usePolled(() => fetchSessionHistory(sessionId), ["history", sessionId], SESSION_POLL_MS, { enabled });
  const instances = usePolled(() => fetchSessionInstances(sessionId), ["instances", sessionId], SESSION_POLL_MS, { enabled });

  const latestAt = latestTimestamp(history.data, instances.data);
  // "Now" is the time of the last poll rather than wall-clock at render, so the
  // indicator is at most one poll interval stale and render stays pure.
  const observedAt = Math.max(history.fetchedAt || 0, instances.fetchedAt || 0) || null;

  let liveState = "unknown";
  if (enabled && run) {
    liveState = runLiveState(run);
  } else if (enabled && latestAt && observedAt) {
    liveState = observedAt - latestAt < LIVE_WINDOW_MS ? "live" : "closed";
  }

  return {
    enabled,
    history: history.data,
    instances: instances.data,
    loading: history.loading || instances.loading,
    error: history.error || instances.error,
    latestAt: run && run.latestAt ? run.latestAt : latestAt,
    startedAt: run ? run.startedAt : null,
    endedAt: run ? run.endedAt : null,
    liveState,
  };
}

function runLiveState(run) {
  if (run.running) return "live";
  return run.latestAt ? "closed" : "unknown";
}

// Run state of every target, from the latest-session fields on /targets:
// which targets are being fuzzed right now, and when the others last were.
// Feeds the header indicator (fleet-wide on the index, one target when
// selected) and its hover list.
export function useFleetLive(tree) {
  const enabled = !!tree && tree.some((e) => e.targets.length > 0);
  const { data } = usePolled(fetchAllTargets, ["fleet"], SESSION_POLL_MS, { enabled });

  const programOf = new Map(tree ? tree.flatMap((e) => e.targets.map((t) => [t.id, e.program.name])) : []);
  const targets = (data || [])
    .filter((t) => t.latest_session_id !== null && t.latest_session_id !== undefined)
    .map((t) => ({
      id: t.id,
      program: programOf.get(t.id) || "",
      focus: t.focus,
      running: Boolean(t.running),
      latestAt: t.latest_reading_at ? new Date(t.latest_reading_at).getTime() || null : null,
      startedAt: t.latest_session_started_at,
      endedAt: t.latest_session_ended_at,
    }))
    .sort((a, b) => Number(b.running) - Number(a.running) || (b.latestAt || 0) - (a.latestAt || 0));

  const running = targets.filter((t) => t.running);
  const withReadings = targets.filter((t) => t.latestAt);
  const latestAt = (running.length ? running : withReadings).reduce((m, t) => Math.max(m, t.latestAt || 0), 0) || null;

  let liveState = "unknown";
  if (enabled && data) liveState = running.length ? "live" : withReadings.length ? "idle" : "unknown";

  const byId = new Map(targets.map((t) => [t.id, t]));
  return { enabled, loaded: Boolean(data), latestAt, liveState, targets, running, byId };
}

// Watches a target's crash count; bumps spikeKey when it grows between polls.
export function useCrashWatch(targetId) {
  const enabled = targetId !== null && targetId !== undefined;
  const [spikeKey, setSpikeKey] = useState(0);
  const prev = useRef({ targetId: null, count: null });

  const onData = (list) => {
    if (prev.current.targetId !== targetId) {
      prev.current = { targetId, count: list.length };
      return;
    }
    if (prev.current.count !== null && list.length > prev.current.count) {
      setSpikeKey((k) => k + 1);
    }
    prev.current.count = list.length;
  };

  const { data, error } = usePolled(() => fetchCrashes(targetId), ["crashes", targetId], CRASH_POLL_MS, {
    enabled,
    onData,
  });

  return { crashes: data, count: data ? data.length : null, error, spikeKey };
}

// Callback ref rather than a layout effect: the measured element is often
// mounted only after data arrives, and a callback ref attaches the observer
// whenever the element actually appears. ResizeObserver delivers an initial
// notification on observe(), so no synchronous measurement is needed.
export function useElementWidth() {
  const [width, setWidth] = useState(0);
  const observer = useRef(null);
  const ref = useCallback((el) => {
    if (observer.current) {
      observer.current.disconnect();
      observer.current = null;
    }
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    observer.current = ro;
  }, []);
  return [ref, width];
}

export function useMediaQuery(query) {
  const subscribe = useCallback(
    (onChange) => {
      const mq = window.matchMedia(query);
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    },
    [query],
  );
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
