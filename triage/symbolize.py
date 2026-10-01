"""
Offline symbolization for CASR reports whose CrashLine / Stacktrace frames
stayed as raw "<module>+0x<offset>" addresses because ASan's inline
symbolizer failed to fork (ENOMEM, intermittent, under memory pressure from
parallel CASR jobs and fuzzers -- see triage/README.md). Resolving these
offline, independent of that runtime memory pressure, fixes two things:
noisy "finding" titles, and dedup silently missing repeats of a site that
only resolved on some of its occurrences.

Runs llvm-symbolizer against the harness binary inside the exact image that
produced the crash (a short-lived `docker run`, never `docker exec` into the
live fuzzer), and only after confirming a BuildId embedded in the raw stack
frames matches that image's binary -- so a stale or rebuilt image can never
resolve an address to the wrong source line.
"""

import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# A bare CrashLine/frame address that never got symbolized, e.g.
# "/fuzzing/harness+0x31dcc4".
MODULE_OFFSET_RE = re.compile(r"^(?P<path>.+)\+0x(?P<offset>[0-9a-fA-F]+)$")

# The same shape embedded in a raw ASan stack frame line, carrying the
# module's Build ID, e.g.:
#   #0 0x55d4... in some_func (/fuzzing/harness+0x31dcc4) (BuildId: 4234abcd)
FRAME_MODULE_OFFSET_RE = re.compile(
    r"\((?P<path>[^()]+)\+0x(?P<offset>[0-9a-fA-F]+)\)\s*\(BuildId:\s*(?P<buildid>[0-9a-fA-F]+)\)"
)

# `readelf -n` / `llvm-readelf -n` build-id note line.
BUILD_ID_RE = re.compile(r"Build ID:\s*([0-9a-fA-F]+)")

# Shell snippet that locates llvm-symbolizer at runtime inside the image:
# the plain name first, else the highest-numbered /usr/bin/llvm-symbolizer-N
# (some base images only ship the versioned binary).
_FIND_SYMBOLIZER_SH = (
    'SYM="$(command -v llvm-symbolizer || true)"; '
    'if [ -z "$SYM" ]; then '
    '  SYM="$(ls /usr/bin/llvm-symbolizer-* 2>/dev/null | sort -V | tail -n1)"; '
    'fi; '
    'if [ -z "$SYM" ]; then echo "no llvm-symbolizer found in image" >&2; exit 1; fi; '
)

_FIND_READELF_SH = (
    'if command -v llvm-readelf >/dev/null 2>&1; then TOOL=llvm-readelf; '
    'else TOOL=readelf; fi; '
)


@dataclass
class ResolveResult:
    crash_line: str
    stacktrace: List[str]
    resolved: bool
    build_id_match: Optional[bool]
    reason: str


_build_id_cache: Dict[Tuple[str, str], Optional[str]] = {}


def run_in_image(
    image: str, shell_cmd: str, stdin_text: Optional[str] = None, timeout: int = 60
) -> subprocess.CompletedProcess:
    """Runs shell_cmd inside a short-lived container from image, bypassing
    whatever ENTRYPOINT the image itself declares."""
    return subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "sh", image, "-c", shell_cmd],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def harness_build_id(image: str, harness_path: str) -> Optional[str]:
    """Build ID (lowercase hex) of harness_path inside image, via
    llvm-readelf/readelf -n. One `docker run` per (image, harness_path),
    cached for the life of the process -- it never changes within a run."""
    key = (image, harness_path)
    if key in _build_id_cache:
        return _build_id_cache[key]

    script = _FIND_READELF_SH + f'exec "$TOOL" -n "{harness_path}"'
    result = run_in_image(image, script)
    build_id = None
    if result.returncode == 0:
        match = BUILD_ID_RE.search(result.stdout)
        if match:
            build_id = match.group(1).lower()
    _build_id_cache[key] = build_id
    return build_id


def _parse_location(line: str) -> Optional[Tuple[str, int, int]]:
    """
    Parses a "file:line:col" (col optional, defaults to 0) location line.
    rsplit-based rather than a single regex: a greedy `(?P<file>.+):` would
    backtrack into matching "file:line" *without* a column by absorbing the
    line number into the file group whenever no column follows, which is
    exactly wrong (same pitfall as api/main.py's crash_file_from_line).
    """
    parts = line.rsplit(":", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and parts[0]:
        file, line_no, col = parts[0], int(parts[1]), int(parts[2])
    else:
        parts = line.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit() and parts[0]:
            file, line_no, col = parts[0], int(parts[1]), 0
        else:
            return None
    if file.startswith("??"):
        return None
    return (file, line_no, col)


def parse_symbolizer_output(
    output: str, offsets: List[str]
) -> Dict[str, Optional[Tuple[str, int, int]]]:
    """
    llvm-symbolizer prints, per input address in order, one (function,
    location) pair per inline level -- innermost first -- then a blank line
    before the next address's pairs. Only the first pair (the innermost
    frame) is used; an unresolved address prints a "??"-prefixed location.
    """
    blocks = output.replace("\r\n", "\n").strip("\n").split("\n\n")
    results: Dict[str, Optional[Tuple[str, int, int]]] = {}
    for offset, block in zip(offsets, blocks):
        lines = [line for line in block.splitlines() if line.strip()]
        location = _parse_location(lines[1].strip()) if len(lines) >= 2 else None
        results[offset] = location
    return results


def symbolize_addresses(
    image: str, harness_path: str, offsets: List[str]
) -> Dict[str, Optional[Tuple[str, int, int]]]:
    """Resolves every address in offsets against harness_path, in exactly
    one container invocation regardless of how many addresses there are."""
    if not offsets:
        return {}
    script = _FIND_SYMBOLIZER_SH + f'exec "$SYM" --obj="{harness_path}"'
    stdin_text = "\n".join(offsets) + "\n"
    result = run_in_image(image, script, stdin_text=stdin_text)
    if result.returncode != 0:
        return {offset: None for offset in offsets}
    return parse_symbolizer_output(result.stdout, offsets)


def _norm_offset(hex_digits: str) -> str:
    return f"0x{hex_digits.lower()}"


def _first_src_frame_location(
    stacktrace: List[str],
    frame_matches: List[Optional[re.Match]],
    resolved: Dict[str, Optional[Tuple[str, int, int]]],
    build_id: str,
) -> Optional[Tuple[str, int, int]]:
    """CASR itself skips sanitizer-runtime frames (no /src/ debug info) when
    picking a crash site. Walking the stack in order -- same order as the
    Stacktrace array, innermost first -- and taking the first frame that
    resolves under /src/ reproduces that when the crash address's own frame
    resolves to "??"."""
    for frame, match in zip(stacktrace, frame_matches):
        if not match or match.group("buildid").lower() != build_id:
            continue
        loc = resolved.get(_norm_offset(match.group("offset")))
        if loc and loc[0].startswith("/src/"):
            return loc
    return None


def resolve_crash_site(
    crash_line: str, stacktrace: List[str], image: Optional[str], harness_path: str
) -> ResolveResult:
    """
    If crash_line is a bare "<module>+0x<offset>" address, tries to resolve
    it (and every matching Stacktrace frame) to source locations using
    offline llvm-symbolizer against harness_path inside image -- but only
    when a BuildId embedded in the raw stack frames matches harness_path's
    actual Build ID in that image. Returns the original values unchanged,
    with resolved=False and a reason, whenever that can't be confirmed.
    """
    crash_line = (crash_line or "").strip()
    stacktrace = list(stacktrace or [])

    module_match = MODULE_OFFSET_RE.match(crash_line)
    if not module_match:
        return ResolveResult(
            crash_line, stacktrace, False, None, "CrashLine is not a raw module+offset address"
        )

    frame_matches = [FRAME_MODULE_OFFSET_RE.search(frame) for frame in stacktrace]
    reported_build_id = next(
        (match.group("buildid").lower() for match in frame_matches if match), None
    )
    if reported_build_id is None:
        return ResolveResult(crash_line, stacktrace, False, None, "no BuildId found in stack frames")

    if not image:
        return ResolveResult(crash_line, stacktrace, False, None, "no image available for symbolization")

    actual_build_id = harness_build_id(image, harness_path)
    if actual_build_id is None:
        return ResolveResult(
            crash_line, stacktrace, False, None,
            f"could not read Build ID of {harness_path} in image {image}",
        )

    if reported_build_id != actual_build_id:
        return ResolveResult(
            crash_line, stacktrace, False, False,
            f"BuildId mismatch (report {reported_build_id}, image {actual_build_id}) "
            "-- wrong or rebuilt binary",
        )

    offsets = {_norm_offset(module_match.group("offset"))}
    for match in frame_matches:
        if match and match.group("buildid").lower() == actual_build_id:
            offsets.add(_norm_offset(match.group("offset")))
    offsets = sorted(offsets)

    resolved = symbolize_addresses(image, harness_path, offsets)

    crash_offset = _norm_offset(module_match.group("offset"))
    crash_loc = resolved.get(crash_offset)
    if crash_loc is None:
        # The crash address itself is unresolvable -- typically because
        # it's inside the sanitizer runtime, which carries no debug info.
        # CASR works around this by walking outward through the stack to
        # the first real application frame; do the same with what this
        # batch already resolved.
        crash_loc = _first_src_frame_location(stacktrace, frame_matches, resolved, actual_build_id)
    if crash_loc is None:
        return ResolveResult(
            crash_line, stacktrace, False, True,
            f"llvm-symbolizer could not resolve {crash_offset}",
        )

    new_crash_line = f"{crash_loc[0]}:{crash_loc[1]}:{crash_loc[2]}"

    new_stacktrace = []
    for frame, match in zip(stacktrace, frame_matches):
        if match and match.group("buildid").lower() == actual_build_id:
            loc = resolved.get(_norm_offset(match.group("offset")))
            if loc:
                frame = f"{frame[:match.start()]}{loc[0]}:{loc[1]}:{loc[2]}{frame[match.end():]}"
        new_stacktrace.append(frame)

    return ResolveResult(new_crash_line, new_stacktrace, True, True, "resolved")
