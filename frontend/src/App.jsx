import { useEffect, useState } from "react";
import { fetchCrashes, fetchProgramTree } from "./api/client";
import { useCrashWatch, useFleetLive, useSessionData } from "./hooks";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Footer from "./components/Footer";
import IndexView from "./components/IndexView";
import TargetList from "./components/TargetList";
import TargetOverview from "./components/TargetOverview";
import CrashDetail from "./components/CrashDetail";
import "./index.css";

const TREE_RETRY_MS = 8000;

async function fetchTargetCounts(targets) {
  const entries = await Promise.all(
    targets.map((t) =>
      fetchCrashes(t.id)
        .then((list) => [t.id, { total: list.length, reported: list.filter((c) => c.status === "reported").length }])
        .catch(() => [t.id, null]),
    ),
  );
  return Object.fromEntries(entries);
}

export default function App() {
  const [tree, setTree] = useState(null);
  const [treeError, setTreeError] = useState(null);
  const [treeAttempt, setTreeAttempt] = useState(0);
  const [counts, setCounts] = useState({});
  const [selection, setSelection] = useState({ programId: null, targetId: null, crashId: null });
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchProgramTree()
      .then((t) => {
        if (!alive) return;
        setTree(t);
        setTreeError(null);
      })
      .catch((e) => alive && setTreeError(e));
    return () => {
      alive = false;
    };
  }, [treeAttempt]);

  // Keep retrying quietly while the index cannot be loaded (e.g. API up but
  // its database tunnel down), so the page recovers without a manual reload.
  useEffect(() => {
    if (!treeError) return undefined;
    const t = setTimeout(() => setTreeAttempt((a) => a + 1), TREE_RETRY_MS);
    return () => clearTimeout(t);
  }, [treeError]);

  const retryTree = () => setTreeAttempt((a) => a + 1);

  const programEntry = tree ? tree.find((e) => e.program.id === selection.programId) : null;
  const program = programEntry ? programEntry.program : null;
  const target = programEntry ? programEntry.targets.find((t) => t.id === selection.targetId) || null : null;
  const sessionId = target ? target.latest_session_id ?? null : null;

  const fleet = useFleetLive(tree);
  const session = useSessionData(sessionId, target ? fleet.byId.get(target.id) || null : null);
  const crashWatch = useCrashWatch(target ? target.id : null);
  // The header shows the selected target's run when one is open, otherwise
  // whether anything at all is being fuzzed; its hover list is always fleet-wide.
  const live = target
    ? { liveState: session.liveState, latestAt: session.latestAt, hasSession: session.enabled, scope: target.focus }
    : { liveState: fleet.liveState, latestAt: fleet.latestAt, hasSession: fleet.enabled, scope: "all targets" };

  // Finding counts for every target, shown in the index and the sidebar;
  // refreshed whenever the watcher notices a new crash on the open target.
  useEffect(() => {
    if (!tree) return undefined;
    let alive = true;
    fetchTargetCounts(tree.flatMap((e) => e.targets)).then((c) => alive && setCounts(c));
    return () => {
      alive = false;
    };
  }, [tree, crashWatch.spikeKey]);

  const selectProgram = (programId) => {
    setSelection({ programId, targetId: null, crashId: null });
    setNavOpen(false);
  };
  const selectTarget = (programId, targetId) => {
    setSelection({ programId, targetId, crashId: null });
    setNavOpen(false);
  };
  const selectCrash = (crashId) => setSelection((s) => ({ ...s, crashId }));
  const clearCrash = () => setSelection((s) => ({ ...s, crashId: null }));
  const clearAll = () => setSelection({ programId: null, targetId: null, crashId: null });

  let view;
  if (selection.crashId) {
    view = (
      <CrashDetail
        key={selection.crashId}
        id={selection.crashId}
        onBack={clearCrash}
        backLabel={target ? `${target.focus} findings` : "back"}
      />
    );
  } else if (target && program) {
    view = (
      <TargetOverview
        program={program}
        target={target}
        session={session}
        crashWatch={crashWatch}
        onSelectCrash={selectCrash}
        onBack={() => selectProgram(program.id)}
      />
    );
  } else if (program) {
    view = (
      <TargetList
        program={program}
        targets={programEntry.targets}
        counts={counts}
        onSelect={(targetId) => selectTarget(program.id, targetId)}
        onBack={clearAll}
      />
    );
  } else {
    view = <IndexView tree={tree} treeError={treeError} counts={counts} onRetry={retryTree} onSelectTarget={selectTarget} />;
  }

  return (
    <div className="shell">
      <Header
        liveState={live.liveState}
        latestAt={live.latestAt}
        hasSession={live.hasSession}
        scope={live.scope}
        targets={fleet.targets}
        currentTargetId={target ? target.id : null}
        onHome={clearAll}
        onToggleMenu={() => setNavOpen((o) => !o)}
      />
      <Sidebar
        tree={tree}
        treeError={treeError}
        counts={counts}
        fleetById={fleet.byId}
        onRetry={retryTree}
        selection={selection}
        onSelectProgram={selectProgram}
        onSelectTarget={selectTarget}
        open={navOpen}
        onClose={() => setNavOpen(false)}
      />
      <main className="main">
        <div className="main-inner">{view}</div>
      </main>
      <Footer programs={tree ? tree.map((e) => e.program) : []} />
    </div>
  );
}
