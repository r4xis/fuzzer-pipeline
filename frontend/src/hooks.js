import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fetchCrashes, fetchSessionHistory, fetchSessionInstances } from "./api/client";

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

export function useSessionData(sessionId) {
  const enabled = sessionId !== null && sessionId !== undefined;
  const history = usePolled(() => fetchSessionHistory(sessionId), ["history", sessionId], SESSION_POLL_MS, { enabled });
  const instances = usePolled(() => fetchSessionInstances(sessionId), ["instances", sessionId], SESSION_POLL_MS, { enabled });

  const latestAt = latestTimestamp(history.data, instances.data);
  // "Now" is the time of the last poll rather than wall-clock at render, so the
  // indicator is at most one poll interval stale and render stays pure.
  const observedAt = Math.max(history.fetchedAt || 0, instances.fetchedAt || 0) || null;

  let liveState = "unknown";
  if (enabled && latestAt && observedAt) {
    liveState = observedAt - latestAt < LIVE_WINDOW_MS ? "live" : "closed";
  }

  return {
    enabled,
    history: history.data,
    instances: instances.data,
    loading: history.loading || instances.loading,
    error: history.error || instances.error,
    latestAt,
    liveState,
  };
}

// Live/closed state across every target, for the header when nothing is
// selected: the newest reading from any target's latest session.
export function useFleetLive(tree) {
  const sessionIds = tree
    ? tree.flatMap((e) => e.targets.map((t) => t.latest_session_id).filter((id) => id !== null && id !== undefined))
    : [];
  const enabled = sessionIds.length > 0;
  const { data, fetchedAt } = usePolled(
    () => Promise.all(sessionIds.map((id) => fetchSessionHistory(id).catch(() => []))),
    ["fleet", sessionIds.join(",")],
    SESSION_POLL_MS,
    { enabled },
  );

  const latestAt = data ? latestTimestamp(data.flat(), null) : null;
  let liveState = "unknown";
  if (enabled && latestAt && fetchedAt) {
    liveState = fetchedAt - latestAt < LIVE_WINDOW_MS ? "live" : "closed";
  }
  return { enabled, latestAt, liveState };
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
