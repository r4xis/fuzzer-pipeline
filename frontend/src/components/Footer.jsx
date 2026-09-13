const PIPELINE_REPO_URL = "https://github.com/placeholder/fuzzer-pipeline";

export default function Footer({ programs }) {
  return (
    <footer className="site-footer">
      <p className="footer-about">
        A running record of memory-safety findings from continuous coverage-guided fuzzing of
        open-source software. Findings are held privately until they have been triaged and
        reported to the maintainers; only reported findings expose technical detail and
        proof-of-concept inputs here.
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
        <span className="faint">AFL++ · CASR · coverage sampled every 15 min</span>
      </div>
    </footer>
  );
}
