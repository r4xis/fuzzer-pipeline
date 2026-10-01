#!/usr/bin/env python3
"""
Unit tests for triage/symbolize.py. Pure parsing/decision logic only -- no
database, and every docker/subprocess call is mocked, so this never touches
a real container. Run with:

    python3 -m unittest discover -s triage/tests
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import symbolize  # noqa: E402  (after the sys.path tweak above)
from symbolize import (  # noqa: E402
    FRAME_MODULE_OFFSET_RE,
    MODULE_OFFSET_RE,
    parse_symbolizer_output,
    resolve_crash_site,
)

IMAGE = "fuzzer-pipeline-fuzzer0@sha256:deadbeef"
HARNESS = "/fuzzing/harness"
BUILD_ID = "4234abcd1234abcd1234abcd1234abcd1234abcd"
OTHER_BUILD_ID = "ffffffffffffffffffffffffffffffffffffffff"

RAW_CRASH_LINE = f"{HARNESS}+0x31dcc4"
RAW_FRAME = (
    f"    #0 0x55d4a1b2c3d4 in some_func ({HARNESS}+0x31dcc4) (BuildId: {BUILD_ID})"
)
RAW_FRAME_2 = (
    f"    #1 0x55d4a1b2c400 in caller_func ({HARNESS}+0x320000) (BuildId: {BUILD_ID})"
)
# A frame inside the sanitizer runtime (statically linked into the same
# harness binary, so same module path and BuildId) that resolves to a real
# location -- just not one under /src/, since compiler-rt's own sources
# live elsewhere.
RAW_FRAME_RUNTIME = (
    f"    #1 0x55d4a1b2c450 in __asan_report_error ({HARNESS}+0x7f0000) (BuildId: {BUILD_ID})"
)
SYMBOLIZED_FRAME = "    #2 0x55d4a1b2c500 in main /src/libvgm/main.c:10:1"

# A real crash: the top three frames are deep in the ASan runtime/allocator
# and libc, raw and unresolvable (no debug info at all, not even outside
# /src/); #3 is the first application frame, and CASR's own inline
# symbolizer managed to resolve it even though it failed on the others.
REAL_CRASH_LINE = f"{HARNESS}+0x38e590"
REAL_FRAME_0 = (
    f"    #0 0xaaaaaad... in __aarch64_cas1_acq_rel ({HARNESS}+0x38e590) (BuildId: {BUILD_ID})"
)
REAL_FRAME_1 = (
    "    #1 0xaaaaaad... in __asan::Allocator::Deallocate "
    f"({HARNESS}+0x54b7c) (BuildId: {BUILD_ID})"
)
REAL_FRAME_2 = f"    #2 0xaaaaaad... in free ({HARNESS}+0xf7490) (BuildId: {BUILD_ID})"
REAL_FRAME_3 = (
    "    #3 0xaaaaaadba97c in device_stop_k054539 "
    "/src/libvgm/emu/cores/k054539.c:657:2"
)


class ParseFrameAddressesTest(unittest.TestCase):
    """Parsing BuildId and offsets out of a CrashLine / raw stack frame."""

    def test_module_offset_crash_line(self):
        match = MODULE_OFFSET_RE.match(RAW_CRASH_LINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("path"), HARNESS)
        self.assertEqual(match.group("offset"), "31dcc4")

    def test_already_symbolized_crash_line_does_not_match(self):
        self.assertIsNone(MODULE_OFFSET_RE.match("/src/libvgm/player/dblk_compr.c:37:15"))

    def test_frame_module_offset_and_build_id(self):
        match = FRAME_MODULE_OFFSET_RE.search(RAW_FRAME)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("path"), HARNESS)
        self.assertEqual(match.group("offset"), "31dcc4")
        self.assertEqual(match.group("buildid"), BUILD_ID)

    def test_symbolized_frame_has_no_module_offset_match(self):
        self.assertIsNone(FRAME_MODULE_OFFSET_RE.search(SYMBOLIZED_FRAME))


class ResolveCrashSiteTest(unittest.TestCase):
    """resolve_crash_site()'s gating logic -- BuildId check and when it
    does/doesn't touch crash_line/stacktrace."""

    def test_already_symbolized_crash_line_is_left_alone(self):
        stacktrace = [SYMBOLIZED_FRAME]
        result = resolve_crash_site("/src/libvgm/main.c:10:1", stacktrace, IMAGE, HARNESS)
        self.assertFalse(result.resolved)
        self.assertIsNone(result.build_id_match)
        self.assertEqual(result.crash_line, "/src/libvgm/main.c:10:1")
        self.assertEqual(result.stacktrace, stacktrace)

    def test_no_build_id_in_frames_is_left_unchanged(self):
        # A raw-looking address but no "(BuildId: ...)" anywhere in the
        # stack -- nothing to verify against, so nothing is resolved.
        stacktrace = ["    #0 0x55d4 in some_func (/fuzzing/harness+0x31dcc4)"]
        with patch.object(symbolize, "harness_build_id") as mock_build_id:
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)
        mock_build_id.assert_not_called()
        self.assertFalse(result.resolved)
        self.assertIsNone(result.build_id_match)
        self.assertEqual(result.crash_line, RAW_CRASH_LINE)
        self.assertEqual(result.stacktrace, stacktrace)

    def test_no_image_is_left_unchanged_without_touching_docker(self):
        stacktrace = [RAW_FRAME]
        with patch.object(symbolize, "harness_build_id") as mock_build_id:
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, None, HARNESS)
        mock_build_id.assert_not_called()
        self.assertFalse(result.resolved)
        self.assertIsNone(result.build_id_match)
        self.assertEqual(result.crash_line, RAW_CRASH_LINE)

    def test_build_id_mismatch_leaves_crash_line_and_stacktrace_unchanged(self):
        stacktrace = [RAW_FRAME, RAW_FRAME_2]
        with patch.object(symbolize, "harness_build_id", return_value=OTHER_BUILD_ID) as mock_build_id, \
             patch.object(symbolize, "symbolize_addresses") as mock_symbolize:
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        mock_build_id.assert_called_once_with(IMAGE, HARNESS)
        mock_symbolize.assert_not_called()  # a mismatch must never even attempt resolution
        self.assertFalse(result.resolved)
        self.assertFalse(result.build_id_match)
        self.assertEqual(result.crash_line, RAW_CRASH_LINE)
        self.assertEqual(result.stacktrace, stacktrace)
        self.assertIn(OTHER_BUILD_ID, result.reason)
        self.assertIn(BUILD_ID, result.reason)

    def test_build_id_match_resolves_crash_line_and_matching_frames_in_one_call(self):
        stacktrace = [RAW_FRAME, RAW_FRAME_2, SYMBOLIZED_FRAME]
        resolved = {
            "0x31dcc4": ("/src/libvgm/player/dblk_compr.c", 37, 15),
            "0x320000": ("/src/libvgm/player/vgmplayer.c", 120, 3),
        }
        with patch.object(symbolize, "harness_build_id", return_value=BUILD_ID), \
             patch.object(symbolize, "symbolize_addresses", return_value=resolved) as mock_symbolize:
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        mock_symbolize.assert_called_once()  # one batched container invocation, not one per frame
        call_args = mock_symbolize.call_args.args
        self.assertEqual(call_args[0], IMAGE)
        self.assertEqual(call_args[1], HARNESS)
        self.assertEqual(sorted(call_args[2]), ["0x31dcc4", "0x320000"])

        self.assertTrue(result.resolved)
        self.assertTrue(result.build_id_match)
        self.assertEqual(result.crash_line, "/src/libvgm/player/dblk_compr.c:37:15")
        self.assertIn("/src/libvgm/player/dblk_compr.c:37:15", result.stacktrace[0])
        self.assertIn("/src/libvgm/player/vgmplayer.c:120:3", result.stacktrace[1])
        # already-symbolized frames pass through untouched
        self.assertEqual(result.stacktrace[2], SYMBOLIZED_FRAME)

    def test_build_id_match_but_symbolizer_cannot_resolve_crash_address(self):
        stacktrace = [RAW_FRAME]
        with patch.object(symbolize, "harness_build_id", return_value=BUILD_ID), \
             patch.object(symbolize, "symbolize_addresses", return_value={"0x31dcc4": None}):
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        self.assertFalse(result.resolved)
        self.assertTrue(result.build_id_match)
        self.assertEqual(result.crash_line, RAW_CRASH_LINE)
        self.assertEqual(result.stacktrace, stacktrace)

    def test_unresolvable_crash_frame_falls_back_to_first_src_frame(self):
        # #0 (the crash address) is inside the sanitizer runtime and has no
        # debug info ("??"); #1 resolves, but not under /src/; #2 is the
        # first real application frame. CASR itself would walk past #0/#1
        # the same way.
        stacktrace = [RAW_FRAME, RAW_FRAME_RUNTIME, RAW_FRAME_2]
        resolved = {
            "0x31dcc4": None,
            "0x7f0000": ("/usr/lib/llvm/compiler-rt/asan_errors.cpp", 100, 1),
            "0x320000": ("/src/libvgm/player/dblk_compr.c", 37, 15),
        }
        with patch.object(symbolize, "harness_build_id", return_value=BUILD_ID), \
             patch.object(symbolize, "symbolize_addresses", return_value=resolved):
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        self.assertTrue(result.resolved)
        self.assertTrue(result.build_id_match)
        self.assertEqual(result.crash_line, "/src/libvgm/player/dblk_compr.c:37:15")
        # #0 couldn't be resolved at all, so it's left raw
        self.assertEqual(result.stacktrace[0], RAW_FRAME)
        # #1 resolved fine (just not under /src/), so it's still rewritten
        self.assertIn("/usr/lib/llvm/compiler-rt/asan_errors.cpp:100:1", result.stacktrace[1])
        self.assertIn("/src/libvgm/player/dblk_compr.c:37:15", result.stacktrace[2])

    def test_unresolvable_crash_frame_with_no_src_frame_anywhere_keeps_raw(self):
        # #0 is unresolvable and #1 resolves but not under /src/ -- no frame
        # ever qualifies, so the raw CrashLine is kept.
        stacktrace = [RAW_FRAME, RAW_FRAME_RUNTIME]
        resolved = {
            "0x31dcc4": None,
            "0x7f0000": ("/usr/lib/llvm/compiler-rt/asan_errors.cpp", 100, 1),
        }
        with patch.object(symbolize, "harness_build_id", return_value=BUILD_ID), \
             patch.object(symbolize, "symbolize_addresses", return_value=resolved):
            result = resolve_crash_site(RAW_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        self.assertFalse(result.resolved)
        self.assertTrue(result.build_id_match)
        self.assertEqual(result.crash_line, RAW_CRASH_LINE)
        self.assertEqual(result.stacktrace, stacktrace)

    def test_falls_back_to_a_frame_casr_already_symbolized_on_its_own(self):
        # Real case: #0-#2 are raw and totally unresolvable (deep in the
        # ASan allocator / libc, no debug info at all); #3 was already
        # symbolized by CASR's own inline symbolizer. The fallback must
        # recognize #3's already-resolved text, not just raw frames this
        # batch resolved itself.
        stacktrace = [REAL_FRAME_0, REAL_FRAME_1, REAL_FRAME_2, REAL_FRAME_3]
        resolved = {"0x38e590": None, "0x54b7c": None, "0xf7490": None}
        with patch.object(symbolize, "harness_build_id", return_value=BUILD_ID), \
             patch.object(symbolize, "symbolize_addresses", return_value=resolved):
            result = resolve_crash_site(REAL_CRASH_LINE, stacktrace, IMAGE, HARNESS)

        self.assertTrue(result.resolved)
        self.assertTrue(result.build_id_match)
        self.assertEqual(result.crash_line, "/src/libvgm/emu/cores/k054539.c:657:2")
        # raw, unresolvable frames are left untouched
        self.assertEqual(result.stacktrace[0], REAL_FRAME_0)
        self.assertEqual(result.stacktrace[1], REAL_FRAME_1)
        self.assertEqual(result.stacktrace[2], REAL_FRAME_2)
        # already-symbolized frame passes through unchanged too
        self.assertEqual(result.stacktrace[3], REAL_FRAME_3)


class ParseSymbolizerOutputTest(unittest.TestCase):
    """Parsing llvm-symbolizer's batch stdin output, including inlined
    frames (innermost -- the first pair in a block -- wins)."""

    def test_single_non_inlined_address(self):
        output = "not_inlined\n/src/t.c:5:35\n"
        result = parse_symbolizer_output(output, ["0x1150"])
        self.assertEqual(result["0x1150"], ("/src/t.c", 5, 35))

    def test_inlined_chain_innermost_wins(self):
        # Real llvm-symbolizer shape for one address with two levels of
        # inlining: innermost function/location pair first.
        output = (
            "inner\n/src/t.c:3:40\n"
            "middle\n/src/t.c:4:36\n"
            "outer\n/src/t.c:5:21\n"
        )
        result = parse_symbolizer_output(output, ["0x1142"])
        self.assertEqual(result["0x1142"], ("/src/t.c", 3, 40))

    def test_batch_of_three_addresses_separated_by_blank_lines(self):
        output = (
            "middle\n/src/t2.c:4:51\n"
            "outer\n/src/t2.c:5:21\n"
            "\n"
            "inner\n/src/t2.c:3:40\n"
            "middle\n/src/t2.c:4:36\n"
            "outer\n/src/t2.c:5:21\n"
            "\n"
            "outer\n/src/t2.c:5:37\n"
            "\n"
        )
        offsets = ["0x1148", "0x1142", "0x114e"]
        result = parse_symbolizer_output(output, offsets)
        self.assertEqual(result["0x1148"], ("/src/t2.c", 4, 51))
        self.assertEqual(result["0x1142"], ("/src/t2.c", 3, 40))  # innermost of its inline chain
        self.assertEqual(result["0x114e"], ("/src/t2.c", 5, 37))

    def test_unresolved_address_is_none(self):
        output = "_end\n??:0:0\n"
        result = parse_symbolizer_output(output, ["0xdeadbeef"])
        self.assertIsNone(result["0xdeadbeef"])


if __name__ == "__main__":
    unittest.main()
