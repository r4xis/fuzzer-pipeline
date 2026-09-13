const PIPELINE_REPO_URL = "https://github.com/r4xis/fuzzer-pipeline";

export default function Footer({ programs }) {
  return (
    <footer className="site-footer">
      <p className="footer-about">
        Memory-safety findings from continuous, coverage-guided fuzzing. Findings stay private
        until they have been reported to the maintainers; only reported findings expose technical
        detail and proof-of-concept inputs.
      </p>
      <div className="footer-links">
        <a href={PIPELINE_REPO_URL} target="_blank" rel="noreferrer">fuzzing pipeline source →</a>
        {(programs || [])
          .filter((p) => p.repo_url)
          .map((p) => (
            <a key={p.id} href={p.repo_url} target="_blank" rel="noreferrer">
              target: {p.name} →
            </a>
          ))}
        <span className="faint">Powered by r4xis</span>
      </div>
    </footer>
  );
}
