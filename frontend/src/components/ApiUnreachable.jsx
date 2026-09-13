import { API_BASE } from "../api/client";

function describe(error) {
  const msg = String((error && error.message) || error || "");
  const status = msg.match(/^(\d{3}) (\/\S*)/);
  if (status) return `The API returned HTTP ${status[1]} for ${status[2]}.`;
  return `The API at ${API_BASE} did not respond.`;
}

export default function ApiUnreachable({ error, onRetry, compact = false }) {
  if (compact) {
    return (
      <div className="notice notice-compact">
        <span className="notice-title">API unreachable</span>
        {onRetry && (
          <button className="btn-retry" onClick={onRetry}>retry</button>
        )}
      </div>
    );
  }
  return (
    <div className="notice">
      <p className="notice-title">Backend unavailable</p>
      <p className="notice-text">
        {describe(error)} The page will retry on its own; if this persists, check that the API server is
        running and that its database connection (or tunnel) is up.
      </p>
      {onRetry && (
        <button className="btn-retry" onClick={onRetry}>Retry now</button>
      )}
    </div>
  );
}
