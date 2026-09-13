import { useEffect, useState } from "react";
import { fetchProgramTree } from "./api/client";
import { useCrashWatch, useSessionData } from "./hooks";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import Footer from "./components/Footer";
import SignalTrace from "./components/SignalTrace";
import IndexView from "./components/IndexView";
import TargetList from "./components/TargetList";
import TargetOverview from "./components/TargetOverview";
import CrashDetail from "./components/CrashDetail";
import "./index.css";

const TREE_RETRY_MS = 8000;

export default function App() {
  const [tree, setTree] = useState(null);
  const [treeError, setTreeError] = useState(null);
  const [treeAttempt, setTreeAttempt] = useState(0);
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

  const session = useSessionData(sessionId);
  const crashWatch = useCrashWatch(target ? target.id : null);

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
        onSelect={(targetId) => selectTarget(program.id, targetId)}
        onBack={clearAll}
      />
    );
  } else {
    view = <IndexView tree={tree} treeError={treeError} onRetry={retryTree} onSelectTarget={selectTarget} />;
  }

  return (
    <div className="shell">
      <Header
        liveState={session.liveState}
        latestAt={session.latestAt}
        hasTarget={Boolean(target)}
        hasSession={session.enabled}
        onHome={clearAll}
        onToggleMenu={() => setNavOpen((o) => !o)}
      />
      <Sidebar
        tree={tree}
        treeError={treeError}
        onRetry={retryTree}
        selection={selection}
        onSelectProgram={selectProgram}
        onSelectTarget={selectTarget}
        open={navOpen}
        onClose={() => setNavOpen(false)}
      />
      <main className="main">
        <div className="main-inner">
          <SignalTrace
            instances={target ? session.instances : null}
            spikeKey={crashWatch.spikeKey}
            live={Boolean(target) && session.liveState === "live"}
          />
          {view}
        </div>
      </main>
      <Footer programs={tree ? tree.map((e) => e.program) : []} />
    </div>
  );
}
