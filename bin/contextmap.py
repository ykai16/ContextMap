import os
import sys
import re
import json
import argparse
import datetime
from typing import List, Dict

__version__ = "1.4.0"

# No external dependencies required for CLI-piping mode

def clean_ansi(text: str) -> str:
    """Removes ANSI escape sequences (colors, cursor moves) from raw terminal logs."""
    # 1. Remove CSI sequences (Cursor movements, colors, etc.)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    # 2. Remove other control characters but keep newlines
    text = re.sub(r'[\x00-\x09\x0B\x0C\x0E-\x1F\x7F]', '', text)
    return text

def smart_compress_transcript(raw_text: str) -> str:
    """
    Intelligently compresses the session log to keep the 'Narrative'
    but discard the 'Bulk Data' (like large file reads, long outputs).
    """
    cleaned = clean_ansi(raw_text)
    lines = cleaned.split('\n')
    compressed = []

    for line in lines:
        line_strip = line.strip()

        # 1. Detect User Prompt (Common CLI prompts)
        if line_strip.startswith("> ") or line_strip.startswith("❯ "):
            compressed.append(f"\n--- USER STEP ---\n{line_strip}")
            continue

        # 2. Skip useless progress lines (heuristic)
        if "Resolving..." in line or "Fetching..." in line or "Downloading..." in line:
            continue

        # 3. Truncate extremely long lines (like base64 or minified code)
        if len(line) > 300:
            line = line[:100] + f" ... [{len(line)-200} chars truncated] ... " + line[-100:]

        compressed.append(line)

    return "\n".join(compressed)

def extract_prompt_evolution(raw_text: str) -> str:
    """Extract and sequence ALL user prompts from the session log in order, inferring intent."""
    cleaned = clean_ansi(raw_text)
    lines = cleaned.split('\n')

    RELATIONSHIP_KEYWORDS = {
        'REFINE':    ['more', 'better', 'also', 'additionally', 'improve', 'refine', 'update', 'change', 'adjust', 'cleaner'],
        'CORRECT':   ['wrong', 'incorrect', 'mistake', 'error', 'fix', 'not ', 'instead', 'actually', 'no,', 'wait', 'that is not'],
        'EXPAND':    ['add', 'include', 'extend', 'expand', 'plus', 'and also', 'as well', 'furthermore'],
        'PIVOT':     ['different', 'new idea', 'switch', 'forget', "let's do", 'actually let', 'start over', 'completely'],
        'VERIFY':    ['check', 'confirm', 'is it', 'did you', 'does it', 'test', 'show me', 'what is', 'verify', 'make sure'],
        'FOLLOW_UP': ['ok', 'okay', 'great', 'good', 'thanks', 'now', 'next', 'then', 'alright', 'perfect'],
    }

    def classify_relationship(text: str, index: int) -> str:
        if index == 0:
            return 'INITIAL'
        lower = text.lower()
        for rel, keywords in RELATIONSHIP_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                return rel
        return 'CONTINUATION'

    prompts = []
    current = []

    for line in lines:
        stripped = line.strip()
        if re.match(r'^[>\u276f]\s+\S', stripped) or re.match(r'^\?\s+\S', stripped) or stripped.startswith("Human:") or stripped.startswith("User:"):
            if current:
                prompts.append(" ".join(current))
            current = [stripped]
        elif current:
            if re.match(r'^(Claude|Assistant|AI):|^\s*[\u23bf\u2713\u2717\u25cf\u2022]\s+', stripped) or (stripped == "" and len(current) > 3):
                prompts.append(" ".join(current))
                current = []
            elif stripped:
                current.append(stripped)

    if current:
        prompts.append(" ".join(current))

    if not prompts:
        return "[No structured user prompts detected]"

    res = [f"=== PROMPT EVOLUTION SEQUENCE ({len(prompts)} steps) ==="]
    for i, p in enumerate(prompts):
        rel = classify_relationship(p, i)
        res.append(f"[PROMPT #{i} | {rel}] {p}")

    return "\n".join(res)

def split_transcript_by_prompts(raw_text: str) -> List[str]:
    """
    Split the raw transcript into individual segments at user prompt boundaries.

    Each returned segment contains one user prompt line plus all output
    that follows it up to (but not including) the next user prompt.
    Returns a list of text strings, one per prompt, in order.
    """
    cleaned = clean_ansi(raw_text)
    lines = cleaned.split('\n')

    segments: List[str] = []
    current_lines: List[str] = []
    found_first_prompt = False

    for line in lines:
        stripped = line.strip()
        is_prompt = bool(
            re.match(r'^[>\u276f]\s+\S', stripped) or
            re.match(r'^\?\s+\S', stripped) or
            stripped.startswith("Human:") or
            stripped.startswith("User:")
        )

        if is_prompt:
            if found_first_prompt and current_lines:
                segments.append('\n'.join(current_lines))
                current_lines = []
            found_first_prompt = True

        if found_first_prompt:
            current_lines.append(line)

    if current_lines:
        segments.append('\n'.join(current_lines))

    return segments

def split_log_into_parts(raw_text: str, n_parts: int) -> List[str]:
    """
    Split the raw log into N roughly equal parts at line boundaries.

    Splitting by line count avoids cutting in the middle of a prompt or
    response.  Parts are returned in order; empty parts are dropped.
    """
    if n_parts <= 1:
        return [raw_text]

    lines = raw_text.split('\n')
    part_size = max(1, len(lines) // n_parts)
    parts = []
    for i in range(n_parts):
        start = i * part_size
        end   = start + part_size if i < n_parts - 1 else len(lines)
        part  = '\n'.join(lines[start:end])
        if part.strip():
            parts.append(part)
    return parts if parts else [raw_text]

def filter_thin_segments(segments: List[str], min_response_lines: int = 3) -> List[str]:
    """
    Remove segments caused by terminal redraws.

    A genuine prompt-response pair always has substantive content after the
    prompt line.  Terminal redraws (whole-line refresh, scrollback, resize)
    produce a segment whose 'response' is empty or just a few stray lines
    before the next prompt fires.  Dropping these thin segments filters out
    the noise regardless of whether the prompt text is identical, a prefix,
    or a scrollback copy of an earlier prompt.

    min_response_lines: minimum number of non-empty lines *after* the first
    prompt line for a segment to be kept (default: 3).  Claude Code responses
    are almost always longer than 3 lines, so this threshold safely filters
    redraw artifacts without discarding real exchanges.
    """
    if not segments:
        return segments

    kept = []
    for seg in segments:
        lines = seg.split('\n')
        # Count non-empty lines that come after the opening prompt line
        response_lines = [l for l in lines[1:] if l.strip()]
        if len(response_lines) >= min_response_lines:
            kept.append(seg)

    removed = len(segments) - len(kept)
    if removed > 0:
        print(f"🔍 Deduplication: {len(segments)} raw segments → {len(kept)} unique prompts "
              f"({removed} terminal-redraw duplicates removed)")

    return kept


def parse_transcript(log_path: str):
    """Reads and compresses the log (used for single-pass fallback)."""
    if not os.path.exists(log_path):
        return "", ""
    try:
        with open(log_path, 'r', errors='replace') as f:
            raw_data = f.read()
        return smart_compress_transcript(raw_data), extract_prompt_evolution(raw_data)
    except Exception as e:
        return f"[Error reading log: {str(e)}]", ""

def generate_summary(transcript: str, old_summary: str = "", model: str = None, part_info: str = None) -> str:
    """Uses Claude Code (CLI) itself to maintain the HTML context map."""

    system_prompt = """You are "ContextMap", an AI assistant that analyzes Claude Code session transcripts and produces a self-contained HTML report reconstructing the user's coding journey — with emphasis on how each prompt EVOLVES from and CONNECTS to the others.

═══════════════════════════════════════════════════════════════════════════════
STEP 0 — IDENTIFY UNIQUE USER PROMPTS
═══════════════════════════════════════════════════════════════════════════════
Before any analysis, scan the raw transcript and identify the UNIQUE user
prompts. Terminal logs often contain many duplicate lines caused by screen
redraws, scrollback replays, or keystroke echoes (each character typed may
appear as a separate line after ANSI codes are stripped).

Treat ALL duplicate prompt lines as if they don't exist — analyze only the
FIRST occurrence of each distinct user intent. A line is a duplicate if it
has the same wording OR is clearly a partial version of a later complete
prompt (e.g. "fix the" before "fix the bug in auth.py").

═══════════════════════════════════════════════════════════════════════════════
PURPOSE
═══════════════════════════════════════════════════════════════════════════════
Users work in Claude Code for hours or a full day. By the end, they've lost
track of which problems they tackled, why they shifted direction, what triggered
each new prompt, and how their thinking evolved.

Your job: RECONSTRUCT THE STORY — the chain of intent linking prompt to prompt.

You will receive TWO inputs:
1) === PREVIOUS SESSION HTML ===
   Existing ContextMap HTML (may be empty on first run).
2) === CURRENT SESSION TRANSCRIPT ===
   Compressed terminal transcript of the latest session (or a log part).

═══════════════════════════════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════════════════════════════
- Output EXACTLY ONE complete valid HTML document. No Markdown. No explanation.
- All CSS in <style>, all JS in <script>. No external deps/CDNs/fonts.
- 100% self-contained. Must look polished in any modern browser.

═══════════════════════════════════════════════════════════════════════════════
DO NOT HALLUCINATE
═══════════════════════════════════════════════════════════════════════════════
- Only mention files, commands, errors, outcomes from the transcript/previous HTML.
- If ambiguous, label "Likely" or "Unclear". Never invent.

═══════════════════════════════════════════════════════════════════════════════
PART PROCESSING (large log split into multiple parts)
═══════════════════════════════════════════════════════════════════════════════
When the message contains [PART X/N]:
- This transcript is one section of a larger session split for context-length
  reasons. It is NOT a new session.
- Add the new prompts as additional steps WITHIN THE CURRENT SESSION GROUP
  (do NOT create a new session divider — they are part of the same session).
- Re-generate Narrative bullets and Anchor cards to reflect ALL steps so far.
- Continue step numbering from where the previous HTML left off.
- If this is Part 1/N with no previous HTML: create from scratch as session 1.
- If N=1 (only one part): treat as a complete session (no "in progress" note).

═══════════════════════════════════════════════════════════════════════════════
CORE ANALYSIS: THE EVOLUTION CHAIN
═══════════════════════════════════════════════════════════════════════════════

For each session, analyze the CHAIN OF INTENT connecting prompts:

1. IDENTIFY each meaningful prompt/iteration (group trivial follow-ups).

2. For EACH step, extract (use BULLET POINTS, not paragraphs):
   - Title: descriptive (<= 80 chars)
   - Intent (3-5 bullet points):
     What problem/goal? What prior context led here? Refinement, pivot, or new direction?
   - Expected (1-3 bullet points):
     What did the user hope would happen?
   - Result (3-5 bullet points):
     What concretely happened? Files changed, errors hit, measurements.
     Side-effects or unexpected discoveries.
   - Status: success | partial | failed | in_progress
   - Artifacts: files created/modified (<= 10)

3. TRANSITION TRIGGERS between consecutive steps (1-2 sentences):
   WHY did the user move to the next prompt? This is the connective tissue.

GROUPING: Merge trivial follow-ups, but don't over-merge intent shifts.
Target 5-20 steps per session.

═══════════════════════════════════════════════════════════════════════════════
HTML LAYOUT
═══════════════════════════════════════════════════════════════════════════════

HEADER
  - "ContextMap" in serif font, with accent color on "Map"
  - Project name subtitle
  - Meta pills: updated date, session count, total steps

SESSION NARRATIVE (section id="narrative")
  - Use BULLET POINTS per session — concise, high-level summary
  - Each session gets a labeled group with 3-5 bullets
  - Example format:
    Session 2 · Feb 21
    • Fixed stale cache bug — PUT/DELETE not invalidating Redis keys
    • Resolved N+1 query in get_todos_with_tags() via joinedload()
    • Implemented cursor-based pagination for scalability
    • Added 12 integration tests; caught off-by-one in cursor logic

CONTEXT ANCHOR (section id="anchor")
  - Use a GRID of icon-rich cards (2 columns on desktop, 1 on mobile)
  - Each card has: emoji icon + label + short description
  - Include cards for: Last Working On, Current State, Next Up,
    Open Concern, Key Decision (as applicable)
  - Make it visually lively with icons

EVOLUTION TIMELINE (section id="timeline")
  - Vertical timeline with compact step cards
  - Each card: click to expand/collapse
  - Collapsed: step number + title + status badge + one-line preview
  - Expanded: Intent/Expected/Result as BULLET POINTS (not paragraphs)
  - BETWEEN cards: transition connector (italic text explaining why
    the user moved to the next step)
  - Group by session with labeled dividers
  - Keep text CONCISE — bullets, not essays

OPEN THREADS (section id="threads")
  - Each thread has: emoji icon + title + description + next step
  - If none, "No open threads."

FOOTER
  - "Generated by ContextMap" · timestamp

═══════════════════════════════════════════════════════════════════════════════
VISUAL DESIGN — Claude Code Style
═══════════════════════════════════════════════════════════════════════════════

Model the visual design after the Claude Code documentation website
(code.claude.com). Key characteristics:

COLOR PALETTE (warm, understated dark theme):
  Background:       #1a1a1a
  Elevated surface:  #222222
  Card surface:     #2a2a2a
  Border:           rgba(255,255,255,0.07)
  Text primary:     #e8e4df  (warm off-white)
  Text secondary:   #a09a92  (warm gray)
  Text muted:       #6b6560
  Accent:           #d4a27f  (warm tan/copper)
  Accent dim bg:    rgba(212,162,127,0.12)
  Accent border:    rgba(212,162,127,0.2)
  Success:          #6ec89b
  Warning:          #e0b861
  Error:            #e07a6e
  Info:             #7aade0

TYPOGRAPHY:
  - HEADERS: Georgia or "Times New Roman" SERIF font — gives a warm,
    premium, editorial feel (this is key to the Claude Code aesthetic)
  - BODY: System sans-serif (-apple-system, BlinkMacSystemFont, "Segoe UI")
  - Section labels: 11px uppercase, letter-spacing 1.5-2px, accent color
  - Body: 15px, line-height 1.7
  - Use font-weight sparingly (400 for body, 600 for labels)

CARD STYLE:
  - background: #222222 (slightly elevated from page bg)
  - border: 1px solid rgba(255,255,255,0.07)
  - border-radius: 10px
  - Comfortable padding (24-28px)
  - Hover: slightly lighter border
  - NO heavy shadows, NO glassmorphism — keep it flat and clean

TIMELINE:
  - Thin vertical line (1px, border color)
  - Small dots (9px) colored by status
  - Step cards are compact, expand on click
  - Transition connectors: left border accent, italic muted text

SPECIAL ELEMENTS:
  - Status badges: pill-shaped, status color at 12% opacity bg + status color text
  - Artifact tags: monospace font, accent dim background, accent border, 4px radius
  - Meta pills: small rounded pills with surface bg
  - Session dividers: uppercase accent-colored label with subtle line
  - Use emoji icons generously in anchor section and open threads

LAYOUT:
  - Max width: 880px centered
  - Generous vertical spacing between sections (48px)
  - Responsive: stacks on mobile

ANIMATIONS:
  - Subtle fade-in on load (CSS @keyframes, staggered delays)
  - Hover transitions on cards (0.2s ease border-color change)
  - Keep animations minimal and tasteful

═══════════════════════════════════════════════════════════════════════════════
ANTI-BLOAT / COMPACTION
═══════════════════════════════════════════════════════════════════════════════
1. Most recent 30 steps in full detail.
2. Older steps → collapsible "Archived History" (title + status + one-line).
3. Narrative and Anchor always reflect latest state.
4. Stay under ~250 KB. No raw transcript. No duplication.

═══════════════════════════════════════════════════════════════════════════════
MERGE / UPDATE
═══════════════════════════════════════════════════════════════════════════════
When previous HTML exists (and NOT a checkpoint update within the same session):
1. Parse existing steps. Add new steps as a new session group.
2. Re-generate Narrative and Anchor for all history.
3. Re-generate transitions (including cross-session).
4. Compact if >30 steps. Preserve step numbering.

When empty: first session, create from scratch.

═══════════════════════════════════════════════════════════════════════════════
JAVASCRIPT (minimal, under 20 lines)
═══════════════════════════════════════════════════════════════════════════════
- Click-to-expand step cards (collapsed by default, show preview only)
- Toggle archived history section
- No external libraries.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL REMINDERS
═══════════════════════════════════════════════════════════════════════════════
1. Output = complete HTML document ONLY. No ```html fences.
2. Transition triggers between steps are ESSENTIAL — never skip them.
3. Use BULLET POINTS for intent/expected/result — concise, not wordy.
4. Session narrative = bullet points per session, high-level and scannable.
5. Anchor section = icon-rich grid cards, visually lively.
6. Typography: SERIF for headers (Georgia), sans-serif for body.
7. Accent color: warm tan #d4a27f — NOT blue/purple gradients.
8. Include specific file names, function names, concrete outcomes.
"""

    # Add part context when log was split into multiple parts
    part_note = ""
    if part_info:
        part_note = (
            f"\n\n[PART {part_info}] "
            "This transcript is one part of a larger session split for context-length reasons. "
            "Add the new prompts as additional steps WITHIN THE CURRENT SESSION GROUP "
            "(do NOT create a new session divider). "
            "Continue step numbering from where the previous HTML left off."
        )

    prompt_content = (
        f"=== PREVIOUS SESSION HTML ===\n{old_summary}\n\n"
        f"=== CURRENT SESSION TRANSCRIPT ===\n{transcript[-80000:]}"
        f"{part_note}"
    )

    import tempfile
    import subprocess

    tmp_system = None
    tmp_prompt = None

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(system_prompt)
            tmp_system = f.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(prompt_content)
            tmp_prompt = f.name

        real_claude = os.getenv("REAL_CLAUDE_PATH") or "claude"

        with open(tmp_prompt, 'r') as f:
            process = subprocess.run(
                [real_claude, "-p", prompt_content, "--system-prompt", system_prompt],
                text=True,
                capture_output=True
            )

        if process.returncode != 0:
            return f"❌ Claude CLI Error: {process.stderr}"

        return process.stdout

    except Exception as e:
        return f"❌ Execution Error: {str(e)}"
    finally:
        for tmp_path in [tmp_system, tmp_prompt]:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

def cleanup_old_logs(log_dir: str, days: int = 2):
    """Deletes log files older than X days."""
    try:
        abs_log_dir = os.path.abspath(log_dir)
        if not os.path.exists(abs_log_dir):
            return
        cutoff = datetime.datetime.now().timestamp() - (days * 86400)
        count = 0
        for f in os.listdir(abs_log_dir):
            if not f.endswith(".log"):
                continue
            path = os.path.join(abs_log_dir, f)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    count += 1
            except OSError:
                pass
        if count > 0:
            print(f"🧹 Cleaned up {count} old log files.")
    except Exception as e:
        print(f"⚠️  Cleanup warning: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="ContextMap Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.html",
                        help="Output path for the HTML summary")
    parser.add_argument("--model", default=None,
                        help="The model used in the session (informational)")
    parser.add_argument("--parts", type=int, default=1,
                        help="Split the log into N parts for large sessions (default: 1)")
    args = parser.parse_args()

    # ── Resolve output path (fixes crash when --out has no directory component) ──
    if os.path.isabs(args.out):
        out_path = args.out
    else:
        out_path = os.path.join(os.getcwd(), args.out)

    # ── Housekeeping: clean up old log files ─────────────────────────────────
    try:
        log_path = (args.log_file if os.path.isabs(args.log_file)
                    else os.path.join(os.getcwd(), args.log_file))
        log_dir = os.path.dirname(log_path)
        if os.path.isdir(log_dir):
            cleanup_old_logs(log_dir)
    except Exception:
        pass

    print(f"ContextMap v{__version__} - Analyzing session context...")

    # ── Read raw transcript ───────────────────────────────────────────────────
    if not os.path.exists(args.log_file):
        print(f"⚠️  Log file not found: {args.log_file}")
        return

    try:
        with open(args.log_file, 'r', errors='replace') as f:
            raw_data = f.read()
    except Exception as e:
        print(f"❌ Error reading log: {e}")
        return

    # ── Load any existing HTML (for multi-session merging) ───────────────────
    old_summary = ""
    if os.path.exists(out_path):
        try:
            with open(out_path, 'r') as f:
                old_summary = f.read()
        except Exception:
            pass

    # ── Ensure output directory exists ───────────────────────────────────────
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # ── Split log into parts (for large sessions) ─────────────────────────────
    log_parts = split_log_into_parts(raw_data, args.parts)
    total_parts = len(log_parts)

    if total_parts > 1:
        print(f"📊 Log split into {total_parts} part(s) for processing")

    current_html = old_summary

    for i, part in enumerate(log_parts, 1):
        if total_parts > 1:
            print(f"🔄 Processing part {i}/{total_parts} ...")

        transcript = smart_compress_transcript(part)
        if not transcript.strip():
            print(f"   ⚠️  Empty part — skipping.")
            continue

        part_info = f"{i}/{total_parts}" if total_parts > 1 else None

        current_html = generate_summary(
            transcript,
            old_summary=current_html,
            model=args.model,
            part_info=part_info,
        )

        # Save after each part — progress is never lost
        with open(out_path, 'w') as f:
            f.write(current_html)

        if total_parts > 1:
            print(f"   ✅ Part {i}/{total_parts} saved")

    print(f"✨ Context Map saved to: {out_path}")

if __name__ == "__main__":
    main()
