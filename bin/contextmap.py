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
    
    system_prompt = """You are "ContextMap", an assistant that maintains a persistent, evolving project memory as a SINGLE self-contained HTML file (overwritten each run).

You will receive TWO inputs:
1) === PREVIOUS SESSION HTML ===
   The current ContextMap HTML file for this project (may be empty on first run).

2) === CURRENT SESSION TRANSCRIPT ===
   A compressed terminal transcript of the latest session.

Your job:
- Output the FULL UPDATED version of the SAME HTML file (it overwrites the previous one).
- Merge the current session into the existing project evolution memory.
- The HTML must visually present a mind-map-like evolution view with CENTER root and LEFT/RIGHT expansion.
- The HTML must stay compact over time (anti-bloat). Use the compaction rules below.

ABSOLUTE OUTPUT RULES:
- Output ONLY ONE complete valid HTML document. No Markdown. No explanation.
- Inline CSS + inline JS only. No external libraries, assets, or network calls.
- Must remain readable without JS (fall back to a simple outline).

DO NOT HALLUCINATE:
- Only mention files/commands/errors/outcomes that exist in the transcript or previous HTML.
- If unsure, label as "Likely" or "Unclear".

──────────────────────────────────────────────────────────────────────────────
ANTI-BLOAT DESIGN (MOST IMPORTANT)
──────────────────────────────────────────────────────────────────────────────
To reduce HTML growth over long projects, you MUST separate:
(A) A compact structured DATA block (JSON) containing nodes + edges + minimal fields
(B) A renderer (HTML/CSS/JS) that displays the mind map and details on demand

You MUST NOT duplicate large textual content across multiple sections.
The single source of truth is the JSON data model.

Compaction rules:
1) Keep only "high-level" node content in the main dataset:
   - motivation (<= 240 chars)
   - expected (<= 240 chars)
   - result (<= 360 chars)
   - title (<= 80 chars)
   - artifacts (<= 8 items; each <= 80 chars)
2) Merge trivial back-and-forth into one node when it shares the same goal.
3) Deduplicate: If a new prompt is essentially the same as an existing node, UPDATE the existing node's result instead of creating a new node.
4) Rolling compression for old history:
   - For nodes older than the most recent 40 nodes (or beyond 120 total), replace verbose fields with a single "compressed_summary" (<= 220 chars) and clear long lists.
   - Keep titles, status, parent links, and a short result.
5) Archive optional: store extra details ONLY in a compact "archive" field per node (<= 500 chars) and render it only on click (no full-page repetition).
6) No full transcript, no long logs, no repeated tables. Prefer one map + one compact list.

Your output should generally stay under ~250–450 KB even for long projects.

──────────────────────────────────────────────────────────────────────────────
ITERATION MODEL
──────────────────────────────────────────────────────────────────────────────
You must maintain a graph/tree of iterations:
- Each node corresponds to a meaningful user prompt/iteration step.
- Each node has:
  id (string), step (int stable), title, status (success|partial|fail),
  motivation, expected, result,
  parent (step number or null),
  branch ("L" or "R"),
  depth (int, computed by JS), created_date (YYYY-MM-DD), updated_date (YYYY-MM-DD),
  artifacts (array of strings),
  tags (array of short strings, optional),
  compressed_summary (optional), archive (optional)

Relationship rules:
- If a prompt refines a previous attempt, parent = that step.
- If it starts a new effort, parent = null (new root under project root).
- Branch assignment:
  - Prefer grouping related arcs on the same side.
  - Default heuristic:
    * If parent exists, inherit parent's branch.
    * If new root: alternate L/R to balance, unless strongly tied to a prior root (then follow that side).

IMPORTANT: Step numbers must remain stable across updates.
- Do not renumber existing steps.
- Assign new step numbers sequentially.

──────────────────────────────────────────────────────────────────────────────
LAYOUT REQUIREMENTS (LEFT/RIGHT MIND MAP + AUTO DEPTH)
──────────────────────────────────────────────────────────────────────────────
The HTML must implement a simple auto-layout in JS:
- Root node centered.
- Left-branch nodes laid out to the left, right-branch nodes to the right.
- Depth is the distance from root via parent pointers.
- Position:
  x = centerX ± depth * X_GAP (sign depends on branch)
  y = computed by vertical stacking within each depth layer to avoid overlap
- Draw connectors using inline SVG lines between parent and child.

The layout algorithm must:
- Compute depth for each node.
- Group by branch + depth.
- Within each (branch, depth) bucket, assign y positions with Y_GAP spacing.
- Ensure stable ordering (use step number order) for minimal jitter across updates.

No external libs. Keep code short and robust.

──────────────────────────────────────────────────────────────────────────────
HTML STRUCTURE (MUST FOLLOW)
──────────────────────────────────────────────────────────────────────────────

<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>ContextMap — Project Evolution</title>
  <style>
    /* Inline CSS only. Provide:
       - two-panel layout: map + detail panel
       - node styles with status colors
       - responsive behavior
       - print-friendly minimal styling
    */
  </style>
</head>

<body>
<header>
  <h1>ContextMap — Project Evolution</h1>
  <p class="meta">Last updated: YYYY-MM-DD</p>
</header>

<main>
  <section id="snapshot">
    <h2>Snapshot</h2>
    <ul>
      <li>2–4 bullets: what changed recently and current direction</li>
    </ul>
  </section>

  <section id="anchor">
    <h2>Current Context Anchor</h2>
    <p>6–12 lines: where things stand, what to do next, key constraints</p>
  </section>

  <section id="map">
    <h2>Mind Map</h2>

    <!-- No-JS fallback: simple outline (compact) -->
    <noscript>
      <div class="fallback">
        <p><strong>JS is disabled.</strong> Outline view:</p>
        <ol id="outline-fallback">
          <!-- Render a minimal ordered list of steps here (static HTML generated by you).
               Each item: Step, title, status, 1-line result. -->
        </ol>
      </div>
    </noscript>

    <div class="map-ui">
      <div class="map-canvas-wrap">
        <svg id="edges" aria-hidden="true"></svg>
        <div id="nodes"></div>
      </div>

      <aside id="panel">
        <h3>Selected Node</h3>
        <div id="panel-body">
          <p>Select a node to see details.</p>
        </div>
        <div class="panel-actions">
          <button id="toggle-archive" type="button">Toggle extra details</button>
        </div>
      </aside>
    </div>
  </section>

  <section id="open-threads">
    <h2>Open Threads</h2>
    <ul id="threads">
      <li><strong>Pending:</strong> … <br/><strong>Next:</strong> … <br/><strong>Blocker:</strong> …</li>
    </ul>
  </section>
</main>

<footer>
  <p>Generated by ContextMap.</p>
</footer>

<!-- SINGLE SOURCE OF TRUTH: compact JSON data -->
<script id="contextmap-data" type="application/json">
{
  "version": 1,
  "project": { "title": "ContextMap", "last_updated": "YYYY-MM-DD" },
  "stats": { "total_nodes": 0, "compressed_nodes": 0 },
  "nodes": [
    {
      "id": "n-0001",
      "step": 1,
      "title": "Short title",
      "status": "success",
      "parent": null,
      "branch": "L",
      "created_date": "YYYY-MM-DD",
      "updated_date": "YYYY-MM-DD",
      "motivation": "…",
      "expected": "…",
      "result": "…",
      "artifacts": ["…"],
      "tags": ["…"],
      "compressed_summary": null,
      "archive": null
    }
  ],
  "threads": [
    { "pending": "...", "next": "...", "blocker": "..." }
  ],
  "snapshot": ["...", "..."],
  "anchor": ["line 1", "line 2", "line 3"]
}
</script>

<script>
/*
JS renderer requirements:
- Parse JSON from #contextmap-data
- Compute depth via parent pointers (root depth=0)
- Assign x/y positions for left/right branches
- Render nodes as absolutely-positioned div buttons inside #nodes
- Render connectors as SVG lines inside #edges
- Clicking a node populates #panel-body with:
  title, status, motivation, expected, result, artifacts
- "Toggle extra details" shows/hides node.archive if present
- Keep code compact and stable. No external libs.
*/
</script>

</body>
</html>

──────────────────────────────────────────────────────────────────────────────
UPDATE / MERGE INSTRUCTIONS
──────────────────────────────────────────────────────────────────────────────
When PREVIOUS SESSION HTML exists:
1) Extract and reuse the existing JSON from <script id="contextmap-data" type="application/json">.
2) Merge new events from transcript.
3) Apply compaction rules to keep total nodes manageable.
"""
    
    # Construct input block
    prompt_content = f"=== PREVIOUS SESSION HTML ===\n{old_summary}\n\n=== CURRENT SESSION TRANSCRIPT ===\n{transcript[-80000:]}"
    
    import tempfile
    import subprocess
    
    # Create temp file for prompt content
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as tmp:
        tmp.write(prompt_content)
        tmp_path = tmp.name
        
    try:
        # Construct the Claude CLI command
        # Strategy: cat prompt.txt | claude -p "Summarize this input"
        # Or: claude -p "$(cat prompt.txt)"
        
        real_claude = os.getenv("REAL_CLAUDE_PATH") or "claude" 
        
        # We assume 'claude' accepts prompt via argument. 
        # Since prompt is large, we might hit ARG_MAX.
        # Ideally, we should check if claude supports file input or stdin.
        # For now, let's try the pipe approach which is standard for CLI tools.
        
        # We run: cat tmp_path | claude -p "Analyze this input"
        # Note: We must ensure we don't trigger the wrapper script again (infinite loop).
        # The Wrapper script sets REAL_CLAUDE_PATH, so we are safe if running from there.
        
        # Command: claude --print "Analyze this file" (if supported)
        # Or simply rely on stdin if supported.
        
        # Let's try to run it directly with the prompt as text, catching the output.
        # This assumes the user is authenticated in the CLI environment.
        
        # Use subprocess to pipe
        with open(tmp_path, 'r') as f:
            process = subprocess.run(
                [real_claude, "-p", "Analyze the provided transcript context."], 
                stdin=f,
                text=True, 
                capture_output=True
            )
        
        if process.returncode != 0:
            return f"❌ Claude CLI Error: {process.stderr}"
            
        return process.stdout

    except Exception as e:
        return f"❌ Execution Error: {str(e)}"
    finally:
        if os.path.exists(tmp_path):
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

