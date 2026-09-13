import { useEffect, useState } from "react";
import { downloadUrl, fetchCrashDetail } from "../api/client";
import { fmtCompact, fmtDateTime, severityLevel } from "../format";

function LockIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
      <rect x="4" y="9" width="12" height="8.5" rx="1" />
      <path d="M7 9V6.5a3 3 0 0 1 6 0V9" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <path d="M8 2v8m0 0 3-3m-3 3L5 7M3 12.5h10" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SourceBlock({ lines }) {
  return (
    <pre className="code-block">
      {lines.map((line, i) => {
        const hit = line.startsWith("--->");
        return (
          <span key={i} className={hit ? "crash-line-highlight" : undefined}>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

function hostOf(url) {
  try {
    return new URL(url).host + new URL(url).pathname;
  } catch {
    return url;
  }
}

// Mounted with key={id} by the parent, so a different finding remounts it
// with fresh state instead of resetting inside an effect.
export default function CrashDetail({ id, onBack, backLabel }) {
  const [crash, setCrash] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCrashDetail(id)
      .then((c) => alive && setCrash(c))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) {
    return (
      <div>
        <button className="btn-link" onClick={onBack}>← {backLabel}</button>
        <div className="error">failed to load finding #{id}: {String(error.message || error)}</div>
      </div>
    );
  }
  if (!crash) {
    return (
      <div>
        <button className="btn-link" onClick={onBack}>← {backLabel}</button>
        <div className="loading">loading finding #{id}…</div>
      </div>
    );
  }

  const disclosed = crash.status === "reported";
  const downloadable = disclosed && crash.visibility === "public";
  const sev = severityLevel(crash.severity_type);

  return (
    <div>
      <button className="btn-link" onClick={onBack}>← {backLabel}</button>

      <div className="view-header">
        <p className="eyebrow">
          {crash.program_name}
          <span className="sep">/</span>
          {crash.target_focus}
          <span className="sep">·</span>
          finding #{crash.id}
        </p>
        <h1 className="view-title mono">{crash.crash_line}</h1>
        <div className="detail-badges">
          <span className={`sev-badge sev-${sev}`}>{crash.severity_type || "unclassified"}</span>
          {crash.severity_desc && <span className="sev-badge">{crash.severity_desc}</span>}
          <span className={`status-pill status-${crash.status}`}>{crash.status}</span>
        </div>
      </div>

      <dl className="kv">
        <dt>Discovered</dt>
        <dd>{fmtDateTime(crash.discovered_at)}</dd>
        <dt>Status</dt>
        <dd>{crash.status}</dd>
        <dt>Visibility</dt>
        <dd>{crash.visibility}</dd>
        {crash.report_url && (
          <>
            <dt>Reported at</dt>
            <dd>
              <a href={crash.report_url} target="_blank" rel="noreferrer">{hostOf(crash.report_url)}</a>
            </dd>
          </>
        )}
        {disclosed && (
          <>
            <dt>PoC size</dt>
            <dd>{crash.poc_file_size != null ? `${fmtCompact(crash.poc_file_size)} bytes` : "—"}</dd>
            <dt>PoC SHA-256</dt>
            <dd>{crash.poc_file_sha256 || "—"}</dd>
          </>
        )}
      </dl>

      {crash.severity_explain && (
        <div className="section">
          <div className="section-label">Assessment</div>
          <p className="prose muted">{crash.severity_explain}</p>
        </div>
      )}

      {!disclosed && (
        <div className="section">
          <div className="locked-panel">
            <span className="locked-icon"><LockIcon /></span>
            <div>
              <p className="locked-title">Technical detail withheld</p>
              <p className="locked-text">
                This finding is still in the review and disclosure process. Stack trace, source
                context, sanitizer output and the proof-of-concept input are published once the
                finding has been reported to the maintainers.
              </p>
            </div>
          </div>
        </div>
      )}

      {disclosed && (
        <>
          {crash.asan_summary && (
            <div className="section">
              <div className="section-label">Sanitizer summary</div>
              <pre className="code-block">{crash.asan_summary}</pre>
            </div>
          )}

          <div className="section">
            <div className="section-label">Stack trace</div>
            <pre className="code-block">{(crash.stacktrace || []).join("\n") || "—"}</pre>
          </div>

          <div className="section">
            <div className="section-label">Source context</div>
            {crash.source_context && crash.source_context.length ? (
              <SourceBlock lines={crash.source_context} />
            ) : (
              <pre className="code-block">—</pre>
            )}
          </div>

          <div className="section">
            <div className="section-label">Proof of concept</div>
            {downloadable ? (
              <a className="btn-download" href={downloadUrl(crash.id)}>
                <DownloadIcon />
                Download PoC input
              </a>
            ) : (
              <p className="download-note">
                reported, but the PoC input is not public yet — download is enabled once visibility is set to public.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
