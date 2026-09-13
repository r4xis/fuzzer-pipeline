import { fmtRelative } from "../format";

const GITHUB_URL = "https://github.com/r4xis";
const LINKEDIN_URL = "https://www.linkedin.com/in/efecan-cetinkaya/";

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M13.63 13.63h-2.37V9.92c0-.88-.02-2.02-1.23-2.02-1.23 0-1.42.96-1.42 1.96v3.77H6.24V6h2.28v1.04h.03c.32-.6 1.09-1.23 2.25-1.23 2.4 0 2.85 1.58 2.85 3.64v4.18zM3.56 4.96a1.37 1.37 0 1 1 0-2.75 1.37 1.37 0 0 1 0 2.75zm1.19 8.67H2.37V6h2.38v7.63zM14.82 0H1.18C.53 0 0 .52 0 1.15v13.7C0 15.48.53 16 1.18 16h13.64c.65 0 1.18-.52 1.18-1.15V1.15C16 .52 15.47 0 14.82 0z" />
    </svg>
  );
}

function liveLabel(liveState, hasSession) {
  if (liveState === "live") return "Live";
  if (liveState === "closed") return "Closed";
  return hasSession ? "No readings" : "No session";
}

export default function Header({ liveState, latestAt, hasSession, scope, onHome, onToggleMenu }) {
  const cls = `live-indicator is-${liveState}`;
  const goHome = (e) => {
    e.preventDefault();
    onHome();
  };
  return (
    <header className="site-header">
      <div className="brand">
        <button className="menu-btn" onClick={onToggleMenu} aria-label="Toggle navigation">
          Nav
        </button>
        <h1 className="brand-title">
          <a href="/" onClick={goHome}>Crash Disclosure</a>
        </h1>
        <span className="brand-sub">Fuzzing disclosure bulletin</span>
      </div>
      <div className="header-right">
        <div className={cls} title={`Fuzzer activity for ${scope}, inferred from the last recorded reading`}>
          <span className="live-dot" />
          <span>{liveLabel(liveState, hasSession)}</span>
          {latestAt && <span className="live-since">· {fmtRelative(latestAt)}</span>}
        </div>
        <div className="icon-links">
          <a className="icon-link" href={GITHUB_URL} target="_blank" rel="noreferrer" aria-label="GitHub">
            <GitHubIcon />
          </a>
          <a className="icon-link" href={LINKEDIN_URL} target="_blank" rel="noreferrer" aria-label="LinkedIn">
            <LinkedInIcon />
          </a>
        </div>
      </div>
    </header>
  );
}
