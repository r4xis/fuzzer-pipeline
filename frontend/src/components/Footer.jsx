const PIPELINE_REPO_URL = "https://github.com/r4xis/fuzzer-pipeline";

// program is the currently selected program (or null on the index), so the
// footer's upstream link always matches what's on screen instead of listing
// every target regardless of context.
export default function Footer({ program }) {
  return (
    <footer className="site-footer">
      <p className="footer-about">
        Memory-safety findings from continuous, coverage-guided fuzzing. Findings stay private
        until they have been reported to the maintainers; only reported findings expose technical
        detail and proof-of-concept inputs.
      </p>
      <div className="footer-links">
        <a href={PIPELINE_REPO_URL} target="_blank" rel="noreferrer">fuzzing pipeline source →</a>
        {program?.repo_url && (
          <a href={program.repo_url} target="_blank" rel="noreferrer">
            target: {program.name} →
          </a>
        )}
        <span className="faint">Powered by r4xis</span>
      </div>
    </footer>
  );
}
