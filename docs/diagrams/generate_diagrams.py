#!/usr/bin/env python3
"""
Generates the documentation diagrams as SVG (and PNG when a converter is
available) into this directory:

  db-schema.svg / .png            tables, columns and foreign keys
  frontend-components.svg / .png  React component tree, hooks and API client

Run from anywhere: python3 docs/diagrams/generate_diagrams.py
"""

import os
import shutil
import subprocess
import sys

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SANS = "-apple-system, Segoe UI, Helvetica, Arial, sans-serif"
C_TEXT = "#24292f"
C_MUTED = "#57606a"
C_BORDER = "#d0d7de"
C_HEAD = "#1f252d"
C_ROW = "#f6f8fa"
C_PK = "#1a7f37"
C_FK = "#0969da"
C_ACCENT = "#2da44e"
C_NOTE = "#fff8c5"


class Svg:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=13, color=C_TEXT, font=FONT, weight="normal", anchor="start"):
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.add(
            f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{s}</text>'
        )

    def rect(self, x, y, w, h, fill, stroke=C_BORDER, rx=4, sw=1):
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    def polyline(self, points, color=C_FK, arrow=True, dash=None):
        pts = " ".join(f"{x},{y}" for x, y in points)
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"{marker}{dash_attr}/>')

    def render(self):
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}">'
            '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{C_FK}"/></marker></defs>'
            f'<rect width="{self.width}" height="{self.height}" fill="#ffffff"/>'
        )
        return head + "".join(self.parts) + "</svg>"


# ---------------------------------------------------------------- db schema

ROW_H = 20
HEAD_H = 30


def table(svg, x, y, w, name, columns):
    """columns: list of (name, type, flag) where flag is '', 'PK', 'FK' or 'UQ'."""
    h = HEAD_H + ROW_H * len(columns) + 10
    svg.rect(x, y, w, h, "#ffffff")
    svg.rect(x, y, w, HEAD_H, C_HEAD, stroke=C_HEAD)
    svg.text(x + 12, y + 20, name, size=14, color="#ffffff", weight="bold")
    for i, (col, typ, flag) in enumerate(columns):
        ry = y + HEAD_H + i * ROW_H
        if i % 2 == 0:
            svg.add(f'<rect x="{x + 1}" y="{ry}" width="{w - 2}" height="{ROW_H}" fill="{C_ROW}"/>')
        color = C_PK if flag == "PK" else C_FK if flag == "FK" else C_TEXT
        weight = "bold" if flag in ("PK", "FK") else "normal"
        svg.text(x + 12, ry + 14, col, color=color, weight=weight)
        svg.text(x + w - 12, ry + 14, typ + (f"  {flag}" if flag else ""), color=C_MUTED, size=12, anchor="end")
    return h


def row_center(y, i):
    return y + HEAD_H + i * ROW_H + ROW_H / 2


def db_schema():
    svg = Svg(1400, 720)
    svg.text(40, 26, "Database schema", size=18, font=SANS, weight="bold")
    svg.text(230, 26, "PK primary key · FK foreign key · UQ unique · arrows point from the foreign key to the referenced table", size=12, font=SANS, color=C_MUTED)

    programs = [("id", "serial", "PK"), ("name", "text", "UQ"), ("repo_url", "text", ""), ("created_at", "timestamptz", "")]
    targets = [("id", "serial", "PK"), ("program_id", "int → programs", "FK"), ("focus", "text", ""), ("commit_hash", "text", ""), ("harness_version", "text", ""), ("created_at", "timestamptz", "")]
    crash_targets = [("crash_id", "int → crashes", "FK"), ("target_id", "int → targets", "FK")]
    sessions = [("id", "serial", "PK"), ("target_id", "int → targets", "FK"), ("started_at", "timestamptz", ""), ("ended_at", "timestamptz", ""), ("seed_count", "int", ""), ("total_execs", "bigint", ""), ("coverage_pct", "numeric(5,2)", "")]
    coverage_history = [("id", "serial", "PK"), ("session_id", "int → sessions", "FK"), ("recorded_at", "timestamptz", ""), ("coverage_pct", "numeric(5,2)", ""), ("total_execs", "bigint", "")]
    fuzzer_instances = [("id", "serial", "PK"), ("session_id", "int → sessions", "FK"), ("instance_name", "text", ""), ("coverage_pct", "numeric(5,2)", ""), ("execs_per_sec", "numeric(10,2)", ""), ("crashes_saved", "int", ""), ("recorded_at", "timestamptz", "")]
    crashes = [
        ("id", "serial", "PK"), ("session_id", "int → sessions", "FK"), ("crash_line", "text", ""),
        ("severity_type", "text", ""), ("severity_desc", "text", ""), ("severity_explain", "text", ""),
        ("stacktrace", "text[]", ""), ("asan_summary", "text", ""), ("source_context", "text[]", ""),
        ("input_hash", "text", "UQ"), ("afl_crash_id", "text", ""), ("poc_file_path", "text", ""),
        ("poc_file_size", "int", ""), ("poc_file_sha256", "text", ""), ("visibility", "text", ""),
        ("status", "text", ""), ("discovered_at", "timestamptz", ""), ("report_url", "text", ""),
    ]
    schema_migrations = [("version", "text", "PK"), ("applied_at", "timestamptz", "")]

    # column 1
    table(svg, 40, 40, 400, "programs", programs)
    table(svg, 40, 200, 400, "targets", targets)
    table(svg, 40, 400, 400, "crash_targets", crash_targets)
    # column 2
    table(svg, 520, 40, 400, "sessions", sessions)
    table(svg, 520, 260, 400, "coverage_history", coverage_history)
    table(svg, 520, 440, 400, "fuzzer_instances", fuzzer_instances)
    # column 3
    table(svg, 1000, 40, 360, "crashes", crashes)
    table(svg, 1000, 480, 360, "schema_migrations", schema_migrations)

    # foreign keys
    svg.polyline([(440, row_center(200, 1)), (490, row_center(200, 1)), (490, row_center(40, 0)), (444, row_center(40, 0))])          # targets.program_id → programs
    svg.polyline([(520, row_center(40, 1)), (470, row_center(40, 1)), (470, row_center(200, 0) - 4), (444, row_center(200, 0) - 4)])  # sessions.target_id → targets
    svg.polyline([(440, row_center(400, 1)), (455, row_center(400, 1)), (455, row_center(200, 0) + 4), (444, row_center(200, 0) + 4)])  # crash_targets.target_id → targets
    svg.polyline([(920, row_center(260, 1)), (945, row_center(260, 1)), (945, row_center(40, 0) - 6), (924, row_center(40, 0) - 6)])   # coverage_history.session_id → sessions
    svg.polyline([(920, row_center(440, 1)), (965, row_center(440, 1)), (965, row_center(40, 0) + 4), (924, row_center(40, 0) + 4)])   # fuzzer_instances.session_id → sessions
    svg.polyline([(1000, row_center(40, 1)), (985, row_center(40, 1)), (985, 10), (700, 10), (700, 36)])                                # crashes.session_id → sessions (top edge)
    svg.polyline([(440, row_center(400, 0)), (460, row_center(400, 0)), (460, 660), (1180, 660), (1180, 444)])                          # crash_targets.crash_id → crashes (bottom edge)

    svg.text(40, 700, "Session-level readings (coverage_history) and per-instance readings (fuzzer_instances) are appended every 15 minutes and never overwritten.", size=12, font=SANS, color=C_MUTED)
    return svg.render()


# ------------------------------------------------------- frontend components

def box(svg, x, y, w, h, title, lines=(), fill="#ffffff", title_color=C_TEXT):
    svg.rect(x, y, w, h, fill)
    svg.text(x + 12, y + 20, title, size=13, weight="bold", color=title_color)
    for i, line in enumerate(lines):
        svg.text(x + 12, y + 38 + i * 16, line, size=11.5, color=C_MUTED)


def frontend_components():
    svg = Svg(1400, 800)
    svg.text(40, 26, "Frontend structure", size=18, font=SANS, weight="bold")
    svg.text(230, 26, "frontend/src — components, hooks and the API client; arrows show who renders or feeds whom", size=12, font=SANS, color=C_MUTED)

    box(svg, 40, 50, 380, 160, "App.jsx", [
        "state: tree · treeError · counts · navOpen",
        "selection { programId, targetId, crashId }",
        "derived: program · target · sessionId",
        "hooks: useSessionData · useCrashWatch · useFleetLive",
        "picks the main view from the selection,",
        "feeds Header the live state (target or fleet-wide)",
    ])

    box(svg, 460, 50, 200, 70, "Header", ["live indicator, home link", "GitHub/LinkedIn, nav toggle"])
    box(svg, 680, 50, 200, 70, "Sidebar", ["program → target tree", "finding counts per target"])
    box(svg, 900, 50, 200, 70, "Footer", ["description, pipeline link", "target links from data"])

    svg.text(1292, 158, "view by selection", size=11, font=SANS, color=C_MUTED)
    box(svg, 460, 170, 200, 80, "IndexView", ["programs → target rows", "since date · finding counts"])
    box(svg, 680, 170, 200, 80, "TargetList", ["targets of one program"])
    box(svg, 900, 170, 240, 80, "TargetOverview", ["stat strip · trace · chart", "instances · findings"])
    box(svg, 1160, 170, 200, 80, "CrashDetail", ["gated on status = reported", "report link · PoC download"])

    box(svg, 460, 300, 200, 60, "ApiUnreachable", ["backend-down notice + retry"])
    box(svg, 700, 300, 150, 80, "SignalTrace", ["crashes-saved strip", "per instance, spikes"])
    box(svg, 870, 300, 150, 80, "CoverageChart", ["static, one line per", "instance, scaled y"])
    box(svg, 1040, 300, 150, 80, "InstanceTable", ["latest reading per", "instance, M badge"])
    box(svg, 1210, 300, 150, 80, "CrashList", ["All / Reported tabs", "fetches own list"])

    # hooks column
    svg.text(40, 246, "hooks.js", size=12, font=SANS, color=C_MUTED)
    hooks = [
        ("usePolled(fetcher, identity, interval)", "fetch now + every N ms, results tagged by identity"),
        ("useSessionData(sessionId)", "history + instances / 5 min → liveState (< 20 min)"),
        ("useCrashWatch(targetId)", "crash list every 45 s → count, spikeKey on increase"),
        ("useFleetLive(tree)", "newest reading across all targets → index live state"),
        ("useElementWidth()", "ResizeObserver via callback ref (chart width)"),
        ("useMediaQuery(query)", "useSyncExternalStore (reduced motion)"),
    ]
    for i, (name, desc) in enumerate(hooks):
        y = 258 + i * 62
        box(svg, 40, y, 380, 52, name, [desc])

    # api client
    box(svg, 460, 430, 900, 220, "api/client.js", [
        "fetchPrograms()                 GET /programs",
        "fetchTargets(programId)         GET /targets?program_id=          (+ created_at, latest_session_id)",
        "fetchProgramTree()              programs + their targets, for sidebar and index",
        "fetchCrashes(targetId, {status}) GET /crashes?visibility=private&target_id=&status=   one row per crash site",
        "fetchCrashDetail(id)            GET /crashes/{id}?visibility=private",
        "fetchSessionHistory(id)         GET /sessions/{id}/history",
        "fetchSessionInstances(id)       GET /sessions/{id}/instances",
        "downloadUrl(id)                 GET /crashes/{id}/download        (public rows only)",
        "API_BASE = VITE_API_BASE || http://localhost:8000",
    ])

    box(svg, 460, 690, 440, 70, "format.js", ["fmtPct · fmtCompact · fmtRate · fmtDate · fmtDateTime", "fmtRelative · severityLevel"])
    box(svg, 920, 690, 440, 70, "index.css", ["single stylesheet: tokens, shell grid, sidebar,", "tables, chart, trace, notices, responsive < 860px"], fill=C_NOTE)

    # App renders the header row and the current view: a bus between the rows
    svg.polyline([(420, 130), (440, 130), (440, 145), (1280, 145)], arrow=False)
    for x in (560, 780, 1000):
        svg.polyline([(x, 145), (x, 124)])
    for x in (560, 780, 1020, 1260):
        svg.polyline([(x, 145), (x, 166)])
    svg.text(446, 141, "renders", size=10, font=SANS, color=C_MUTED)
    # TargetOverview → children
    for cx in (775, 945, 1115, 1285):
        svg.polyline([(1020, 250), (1020, 280), (cx, 280), (cx, 296)])
    # ApiUnreachable is used by IndexView and Sidebar
    svg.polyline([(560, 250), (560, 296)])
    svg.polyline([(680, 100), (670, 100), (670, 330), (664, 330)], dash="3 3")
    # client feeds the hooks, CrashList and CrashDetail (they fetch directly)
    svg.polyline([(460, 540), (430, 540), (430, 470), (424, 470)])
    svg.polyline([(1285, 430), (1285, 384)])
    svg.polyline([(1300, 430), (1380, 430), (1380, 210), (1364, 210)])
    # hooks feed App
    svg.polyline([(230, 258), (230, 214)])

    return svg.render()


# ------------------------------------------------------------------ output

def to_png(svg_path, png_path, width, height):
    try:
        import cairosvg  # noqa: F401

        cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=2 * width)
        return "cairosvg"
    except Exception:
        pass
    for tool, cmd in (
        ("rsvg-convert", ["rsvg-convert", "-z", "2", "-o", png_path, svg_path]),
        ("inkscape", ["inkscape", svg_path, "--export-type=png", "--export-dpi=192", f"--export-filename={png_path}"]),
        ("magick", ["magick", "-density", "192", svg_path, png_path]),
        ("convert", ["convert", "-density", "192", svg_path, png_path]),
    ):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=True)
            return tool
    for browser in ("google-chrome", "chromium", "chromium-browser"):
        if shutil.which(browser):
            subprocess.run(
                [browser, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=2",
                 f"--window-size={width},{height}", f"--screenshot={png_path}", f"file://{svg_path}"],
                check=True, capture_output=True,
            )
            return browser
    return None


def main():
    outputs = {"db-schema": (db_schema(), 1400, 720), "frontend-components": (frontend_components(), 1400, 800)}
    for name, (content, width, height) in outputs.items():
        svg_path = os.path.join(OUT_DIR, f"{name}.svg")
        with open(svg_path, "w") as f:
            f.write(content)
        print(f"wrote {svg_path}")
        png_path = os.path.join(OUT_DIR, f"{name}.png")
        tool = to_png(svg_path, png_path, width, height)
        print(f"wrote {png_path} via {tool}" if tool else f"no SVG→PNG converter found; {name}.png not written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
