import { useState } from "react";
import ProgramList from "./components/ProgramList";
import TargetList from "./components/TargetList";
import CrashList from "./components/CrashList";
import CrashDetail from "./components/CrashDetail";
import "./index.css";

function TraceDivider() {
  return (
    <svg className="trace-divider" viewBox="0 0 840 50" role="img" aria-label="signal trace">
      <path
        d="M0,25 L150,25 L165,8 L180,42 L195,25 L340,25 L355,12 L370,38 L385,25 L560,25 L575,6 L590,44 L605,25 L840,25"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.5"
        strokeDasharray="4 3"
      >
        <animate
          attributeName="stroke-dashoffset"
          from="0"
          to="-14"
          dur="1.4s"
          repeatCount="indefinite"
        />
      </path>
    </svg>
  );
}

function App() {
  const [programId, setProgramId] = useState(null);
  const [targetId, setTargetId] = useState(null);
  const [crashId, setCrashId] = useState(null);

  let view;
  if (crashId) {
    view = <CrashDetail id={crashId} onBack={() => setCrashId(null)} />;
  } else if (targetId) {
    view = (
      <CrashList
        targetId={targetId}
        onSelect={setCrashId}
        onBack={() => setTargetId(null)}
      />
    );
  } else if (programId) {
    view = (
      <TargetList
        programId={programId}
        onSelect={setTargetId}
        onBack={() => setProgramId(null)}
      />
    );
  } else {
    view = <ProgramList onSelect={setProgramId} />;
  }

  return (
    <div className="app">
      <header>
        <h1>Crash Disclosure</h1>
      </header>
      <TraceDivider />
      {view}
    </div>
  );
}

export default App;
