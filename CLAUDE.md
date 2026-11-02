# Assembly Tool — Project Memory

An assembly-editing tool for a professional film editor (narrative shorts,
YouTube vlogs, Instagram Reels). It does the mechanical pre-edit work —
sync, transcription, selects, filler removal, beat-grid cutting, color
normalization — and hands off a real, editable timeline. It never makes a
performance or story decision. See NON-NEGOTIABLES below; they are not
aspirational, they are the spec.

## Setup (confirmed with the editor)

| | |
|---|---|
| NLE | **Premiere Pro** — deliverables are OTIO → Premiere XML/AAF, media relinked to camera originals. No live scripting API (unlike Resolve), so every hand-off is file-based: round-trip fidelity into Premiere has to be verified for real, not assumed. |
| Primary project rate | **60p, true (non-drop)** — exact 60.000 fps, not 59.94. |
| Camera / codec | **Sony S-Log3** (A7SIII / FX3 / FX6 family), S-Gamut3.Cine/S-Log3. Needs a correct input transform before any LAB matching, LUT, or grade touches it. |
| Machine | **Windows + GPU** — CUDA available for WhisperX/pyannote. Resolve isn't in play here, so this mainly affects the ML inference stack, not an NLE scripting path. |
| Media drive | **TODO — fill in the path.** Ingest/manifest config will reference this; safe to leave as a placeholder until it's needed (Build Order step 2). |

Even though the primary project rate is 60p NDF, the `Timecode` class supports
the full rate family (23.976/24/25/29.97/30/59.94/60, DF and NDF) because
footage of other native rates will get mixed in from clients/stock/deliverables,
and drop-frame math is exactly the kind of thing that must never be assumed
away. See `src/assembly_tool/timecode.py`.

## Non-negotiables

1. **Frame accuracy is correctness, not a nice-to-have.** Every cut point is
   an integer frame number. Never a float, never a rounded second. Frame
   rates are stored as exact `Fraction`s (e.g. `Fraction(30000, 1001)` for
   29.97), never decimals. Drop-frame timecode must round-trip exactly.
2. **The output is a timeline, not a render.** Deliverables are OTIO, then
   Premiere XML/AAF (per the NLE setting above), with media relinked to
   original camera files. A rendered MP4 is a preview, never the deliverable.
3. **It assembles, it does not decide.** Per Walter Murch's rule of six
   (emotion, story, rhythm, eye-trace, screen plane, spatial continuity, in
   that priority order): everything from rhythm down is mechanical and fair
   game to automate. Emotion and story stay the editor's. Nothing is ever
   silently discarded — soft/clipped/flagged takes stay in the assembly,
   flagged, for the editor to judge.

## Architecture

- **Language/deps**: Python 3.12, managed with `uv`. `pyproject.toml` +
  `uv.lock` are the source of truth for dependencies; don't hand-edit the
  lock file.
- **Layout**: `src/assembly_tool/` (src layout, so tests import the
  installed package rather than accidentally importing from cwd).
  Tests in `tests/`, run via `uv run pytest`.
- **Foundation layer** (`timecode.py`): `FrameRate` (exact `Fraction` +
  name) and `Timecode` (absolute frame number + rate + drop-frame flag).
  Every other module that touches a cut point imports this — there is no
  second source of truth for time anywhere in this codebase. Timecode
  strings are a *display* derived from `frame_number`; arithmetic always
  happens on the integer, never on the string or on seconds-as-float.
- **Interface**: CLI first (per editor's directive — no UI investment until
  the pipeline is proven). Gradio, if ever, comes after Build Order step 8.
- **Build order**: vertical slices, each independently producing a real,
  openable artifact before the next slice starts. See the editor's original
  spec for the full 10-step order (timecode → ingest → OTIO round-trip →
  sync → transcription → vlog mode → reels mode → narrative mode → color →
  interface). This file's decision log tracks actual progress against it.

## Decision log

- **2026-08-24** — Project setup confirmed (table above). Built
  `src/assembly_tool/timecode.py` (`FrameRate`, `Timecode`) and
  `tests/test_timecode.py` (41 tests: NDF round-trips at all 7 standard
  rates, DF round-trips at 29.97/59.94 including an exhaustive full-hour
  sweep, hand-verified SMPTE reference values — the classic 107892-frame
  and 215784-frame one-hour marks — rejection of non-existent DF timecodes,
  and rate-mismatch guards on comparison/subtraction). All passing.
  - Chose to implement drop-frame generally (any nominal-30 or nominal-60
    NTSC-family rate) rather than hardcoding 29.97 only, since the DF
    algorithm is rate-parametric anyway and 59.94 will matter once vertical
    Reels/high-frame-rate footage enters the pipeline.
  - Deliberately did **not** implement frame-rate *conversion* (e.g.
    retiming a 23.976 EDL onto a 29.97 timeline) — that's a separate,
    much riskier feature (requires a defined retiming policy: pulldown,
    frame-blend, drop) and isn't needed until color/finishing steps. Noted
    here so a future session doesn't assume it exists.
  - `Timecode` comparison/subtraction across different rates raises
    `ValueError` rather than silently comparing frame numbers — frame 100
    at 24fps and frame 100 at 60fps are not the same duration, and letting
    `<` or `-` pretend otherwise would be exactly the kind of silent error
    Non-negotiable #1 exists to prevent. (Caught this as a bug in my own
    first draft, which used dataclass `order=True` — that auto-generates
    field-tuple comparison and would have compared `frame_number` first
    without ever checking `rate` matched. Replaced with explicit
    rate-checked `__lt__`/`__le__`/`__gt__`/`__ge__`.)
  - Next: media ingest (Build Order step 2) — probe files, build a JSON
    manifest. Needs the media drive path filled in above first.

## Open questions for the editor

- Media drive path — needed before ingest work starts.
- Confirm 60p NDF is really the delivery/cut rate throughout, or whether
  some projects on this drive are actually 29.97/59.94 DF (e.g. broadcast
  deliverables) — affects what "primary rate" defaults to in the ingest
  manifest.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
