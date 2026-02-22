import os
import sys
import re
import json
import argparse
import datetime
from typing import List, Dict

# No external dependencies required for CLI-piping mode
# try:
#     from openai import OpenAI
# except ImportError:
#     pass # Handled gracefully if needed for fallback

def clean_ansi(text: str) -> str:
    """Removes ANSI escape sequences (colors, cursor moves) from raw terminal logs."""
    # 1. Remove CSI sequences (Cursor movements, colors, etc.)
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    text = ansi_escape.sub('', text)
    
    # 2. Remove other control characters but keep newlines
    # This removes Backspaces (\x08) which can mess up logging
    text = re.sub(r'[\x00-\x09\x0B\x0C\x0E-\x1F\x7F]', '', text)
    return text

def smart_compress_transcript(raw_text: str) -> str:
    """
    Intelligently compresses the session log to keep the 'Narrative' 
    but discard the 'Bulk Data' (like large file reads, long outputs).
    """
    # 1. Clean basic ANSI
    cleaned = clean_ansi(raw_text)
    
    lines = cleaned.split('\n')
    compressed = []
    
    for line in lines:
        line_strip = line.strip()
        
        # 1. Detect User Prompt (Common CLI prompts)
        if line_strip.startswith("> ") or line_strip.startswith("❯ "):
            # Add extra newline for separation
            compressed.append(f"\n--- USER STEP ---\n{line_strip}")
            continue
            
        # 2. Skip useless progress lines (heuristic)
        if "Resolving..." in line or "Fetching..." in line or "Downloading..." in line:
            continue
            
        # 3. Truncate extremely long lines (like base64 or minified code)
        if len(line) > 300:
            line = line[:100] + f" ... [{len(line)-200} chars truncated] ... " + line[-100:]
            
        compressed.append(line)
        
    # Re-join
    full_text = "\n".join(compressed)
    
    # 4. Aggressive block deduplication (if tool output repeats)
    # Use regex to replace massive blocks of similar looking lines (like file reads)
    # This is safer than line-by-line state machines which can break easily
    
    return full_text

def parse_transcript(log_path: str) -> str:
    """Reads and compresses the log."""
    if not os.path.exists(log_path):
        return ""
    
    try:
        with open(log_path, 'r', errors='replace') as f:
            raw_data = f.read()
            
        return smart_compress_transcript(raw_data)
    except Exception as e:
        return f"[Error reading log: {str(e)}]"

def generate_summary(transcript: str, old_summary: str = "", model: str = None) -> str:
    """Uses Claude Code (CLI) itself to maintain the HTML context map."""
    
    system_prompt = """You are "ContextMap", an AI assistant that analyzes Claude Code session transcripts and produces a self-contained HTML report reconstructing the user's coding journey — with emphasis on how each prompt EVOLVES from and CONNECTS to the others.

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
   Compressed terminal transcript of the latest session.

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
When previous HTML exists:
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
    
    # Construct input block (user message with both previous HTML and current transcript)
    prompt_content = f"=== PREVIOUS SESSION HTML ===\n{old_summary}\n\n=== CURRENT SESSION TRANSCRIPT ===\n{transcript[-80000:]}"
    
    import tempfile
    import subprocess
    
    # Create temp files for system prompt and user prompt
    tmp_system = None
    tmp_prompt = None
    
    try:
        # Write system prompt to a temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(system_prompt)
            tmp_system = f.name
        
        # Write user prompt content to a temp file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as f:
            f.write(prompt_content)
            tmp_prompt = f.name
        
        real_claude = os.getenv("REAL_CLAUDE_PATH") or "claude"
        
        # Read the prompt content to pass via stdin
        # Use --system-prompt to pass the system instructions
        # Use -p to pass the user prompt via stdin pipe
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
        # Resolve absolute path just to be sure
        abs_log_dir = os.path.abspath(log_dir)
        
        if not os.path.exists(abs_log_dir):
            return
            
        cutoff = datetime.datetime.now().timestamp() - (days * 86400)
        
        count = 0
        for f in os.listdir(abs_log_dir):
            if not f.endswith(".log"): continue
            
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
        # Housekeeping should never crash the app
        print(f"⚠️  Cleanup warning: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="ContextMap Analyzer")
    parser.add_argument("log_file", help="Path to the raw session log")
    parser.add_argument("--out", default=".context/session_summary.html", help="Output path for summary")
    parser.add_argument("--model", default=None, help="The model used in the session")
    args = parser.parse_args()

    # 0. Cleanup Old Logs (Housekeeping)
    # ROBUST FIX: Explicitly resolve absolute path based on CWD
    # We assume log_file is relative to CWD if not absolute
    try:
        if os.path.isabs(args.log_file):
            log_path = args.log_file
        else:
            log_path = os.path.join(os.getcwd(), args.log_file)
            
        log_dir = os.path.dirname(log_path)
        
        # Only attempt cleanup if directory actually exists
        if os.path.isdir(log_dir):
            cleanup_old_logs(log_dir)
    except Exception:
        # Fail silently on cleanup to prioritize summary generation
        pass

    # 2. Parse & Analyze
    print("🧠 Analyzing session context...")
    transcript = parse_transcript(args.log_file)
    if not transcript.strip():
        print("⚠️  Empty transcript. Nothing to analyze.")
        return

    # Load Previous Summary (Recursive Memory)
    old_summary = ""
    if os.path.exists(args.out):
        try:
            with open(args.out, 'r') as f:
                old_summary = f.read()
        except:
            pass

    # Call summary generation (which now uses Claude CLI subprocess)
    summary = generate_summary(transcript, old_summary=old_summary, model=args.model)
    
    # 3. Save
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w') as f:
        f.write(summary)
    
    print(f"✨ Context Map saved to: {args.out}")

if __name__ == "__main__":
    main()

