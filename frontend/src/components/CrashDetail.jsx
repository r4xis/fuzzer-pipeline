import { useEffect, useState } from "react";
import { fetchCrashDetail } from "../api/client";

export default function CrashDetail({ id, onBack }) {
  const [crash, setCrash] = useState(null);

  useEffect(() => {
    setCrash(null);
    fetchCrashDetail(id).then(setCrash);
  }, [id]);

  if (!crash) return <p className="muted">Loading...</p>;

  return (
    <div className="crash-detail">
      <button className="back-btn" onClick={onBack}>
        &larr; Back
      </button>

      <h2 className="crash-path">{crash.crash_line}</h2>
      <span className="badge">{crash.severity_type}</span>
      <p className="muted">{crash.severity_explain}</p>

      <h3>Stack trace</h3>
      <pre className="code-block">
        {crash.stacktrace?.join("\n")}
      </pre>

      <h3>Source</h3>
      <pre className="code-block">
        {crash.source_context?.map((line, i) => (
          <div
            key={i}
            className={line.startsWith("--->") ? "crash-line-highlight" : ""}
          >
            {line}
          </div>
        ))}
      </pre>
    </div>
  );
}
