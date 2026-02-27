<p align="center">
  <img src=".github/banner.png" alt="ContextMap Banner" width="100%" />
</p>

<p align="center">
  <strong>Session intelligence for <a href="https://docs.anthropic.com/en/docs/claude-code">Claude Code</a>. Never lose your train of thought again.</strong>
</p>

<p align="center">
  <a href="https://github.com/ykai16/ContextMap/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-d4a27f.svg?style=flat-square" alt="License" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.8+-d4a27f.svg?style=flat-square&logo=python&logoColor=white" alt="Python" /></a>
  <a href="https://github.com/ykai16/ContextMap/stargazers"><img src="https://img.shields.io/github/stars/ykai16/ContextMap?style=flat-square&color=d4a27f" alt="Stars" /></a>
  <a href="https://github.com/ykai16/ContextMap/issues"><img src="https://img.shields.io/github/issues/ykai16/ContextMap?style=flat-square&color=e07a6e" alt="Issues" /></a>
  <a href="https://github.com/ykai16/ContextMap/commits/master"><img src="https://img.shields.io/github/last-commit/ykai16/ContextMap?style=flat-square&color=6ec89b" alt="Last Commit" /></a>
</p>

<p align="center">
  <a href="#-quick-start">Quick Start</a> · 
  <a href="#-how-it-works">How It Works</a> · 
  <a href="#%EF%B8%8F-output-example">Example</a> · 
  <a href="#%EF%B8%8F-configuration">Configuration</a> · 
  <a href="#-contributing">Contributing</a>
</p>

---

## 💡 The Problem

You've been coding with Claude Code for hours. You've fixed bugs, refactored modules, chased down edge cases, pivoted strategies. By the end of the session — **you've forgotten the arc of what you accomplished.**

Tomorrow, you'll open your terminal and ask yourself:

> *"Where was I? What did I decide? Why did I go down that path?"*

**ContextMap** solves this. It automatically records your Claude Code sessions and generates a beautiful HTML report that reconstructs your coding journey — showing not just *what* you did, but *why* each prompt led to the next.

## 🎯 Features (v1.2.0)

### ✨ Key Updates in v1.2.0
- **Version Display**: The ContextMap version number is now shown on every `claude` launch — e.g. `🦉 ContextMap v1.2.0 active.`
- **Auto-Update**: ContextMap checks GitHub for a newer version once per day (result cached — zero overhead on subsequent launches). When a new version is found, it automatically runs `git pull` in the ContextMap directory and prompts you to restart your terminal. If the update fails (no network, no git), it silently degrades and optionally shows a manual update command.

### ✨ Key Updates in v1.1.1
- **Checkpoint Mechanism for Long Sessions**: ContextMap now splits any session into groups of 3 prompts and processes them incrementally. Each group is summarized and saved to the HTML file immediately — so even hour-long sessions with dozens of prompts are handled reliably, without hitting context-length limits or losing progress.
  - The HTML is saved after every 3-prompt checkpoint, meaning you never lose work if something fails mid-analysis.
  - The final report is a single cohesive document — no visible seams between checkpoints.
  - Configurable via `--chunk-size N` (default: 3).
- **Fixed Output Path Bug**: `--out` now works correctly with bare filenames (no directory prefix required).

### ✨ Key Updates in v1.02
- **Full Prompt Evolution Tracking**: Diagnosed and fixed an issue where only the last prompt was captured; ContextMap now explicitly extracts and sequences all your prompts so the underlying AI grasps the complete evolution of your intent.
- **Improved Versioning**: The ContextMap version is now clearly identifiable on launch!

### Core Features
- 🔗 **Evolution Chain** — Tracks how prompts connect and evolve, showing the *intent* behind each transition
- 📊 **Rich HTML Reports** — Beautifully styled, self-contained HTML files you can open in any browser
- 🧠 **Session Narrative** — High-level bullet-point summary of each session's accomplishments
- 📍 **Context Anchor** — "Where We Left Off" section so you can resume instantly
- 🔄 **Multi-Session Tracking** — Merges history across sessions into a single evolving report
- 🎨 **Claude Code Aesthetic** — Polished dark theme inspired by Claude Code's design language
- ⚡ **Zero Friction** — Wraps your `claude` command transparently; just use Claude Code as usual
- 🧩 **Long-Session Checkpoint Processing** — Automatically splits and processes long sessions in chunks; no session is too long
- 🔄 **Auto-Update** — Checks GitHub daily and updates itself automatically; always on the latest version

## 🚀 Quick Start

**Prerequisites:** `git`, `python3`, `pip`

```bash
# Clone the repository
git clone https://github.com/ykai16/ContextMap.git
cd ContextMap

# Run the installer
./install.sh
```

Restart your terminal or reload your shell:

```bash
source ~/.zshrc    # or source ~/.bashrc
```

That's it. Now just use `claude` as you normally would — ContextMap runs silently in the background.

## 🧠 How It Works

ContextMap wraps your `claude` command with an intelligent recording layer:

```
┌─────────────────────────────────────────────────────────┐
│  You type: claude                                        │
│                                                          │
│  1. 📄  Load previous session context                   │
│         Display "Previously on..." summary               │
│                                                          │
│  2. 🎙️  Record session transparently                    │
│         All interactions captured via script/pty          │
│                                                          │
│  3. 🧩  Split into checkpoint chunks (every 3 prompts)  │
│         Handles sessions of any length reliably           │
│                                                          │
│  4. 🧠  Analyze each chunk incrementally                │
│         Each group of 3 prompts → LLM → append to HTML  │
│         HTML saved after every checkpoint (never lost)   │
│                                                          │
│  5. 📊  Save final report                               │
│         .context/session_summary.html updated             │
└─────────────────────────────────────────────────────────┘
```

### The Report Structure

Each generated HTML report contains:

| Section | Description |
| :--- | :--- |
| **Session Narrative** | Bullet-point summary of what was accomplished per session |
| **Context Anchor** | Icon-rich grid showing current state, next steps, open concerns |
| **Evolution Timeline** | Step-by-step cards with intent → expected → result + transition triggers |
| **Open Threads** | Unresolved issues, pending tasks, suggested next actions |

### What Makes It Special

Unlike simple session logs, ContextMap captures the **"why"** between prompts:

```
  Step #3: Fix N+1 query                    ✓ SUCCESS
  ├─ Intent:  Response times degraded after cache fix
  ├─ Result:  Switched to joinedload(), 200ms → 40ms
  └─ Artifacts: crud/todos.py, database.py

       ↓  "Performance resolved — shifted to pagination feature"

  Step #4: Implement cursor pagination      ✓ SUCCESS
  ├─ Intent:  Dataset expected to grow to 100k+ items
  ├─ Result:  Cursor-based with WHERE id > cursor
  └─ Artifacts: routers/todos.py, schemas/pagination.py
```

## 🖼️ Output Example

ContextMap generates a polished HTML file at `.context/session_summary.html` in your project root.

<p align="center">
  <em>Warm dark theme · Serif headers · Icon-rich layout · Click-to-expand cards</em>
</p>

The report is **100% self-contained** — no external dependencies, CDNs, or internet required. Just open it in your browser.

> 💡 **Tip:** Check out the [**live example report**](https://raw.githack.com/ykai16/ContextMap/master/examples/example_report.html) to see a full sample — or download [`examples/example_report.html`](examples/example_report.html) and open it locally.

## ⚙️ Configuration

### Zero Config Required

ContextMap uses the **`claude` CLI directly** for session analysis — the same Claude Code you already have installed and authenticated. No separate API key is needed.

> ✅ **If Claude Code works, ContextMap works.** It inherits your existing Claude Code authentication automatically.

### Environment Variables (Optional)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `REAL_CLAUDE_PATH` | Override path to the `claude` binary (useful if you have multiple installations) | auto-detected |

### CLI Options for `contextmap.py`

You normally don't call `contextmap.py` directly — `wrapper.py` does it for you on session exit. But you can also run it manually:

```bash
python3 bin/contextmap.py <log_file> [--out PATH] [--chunk-size N] [--model NAME]
```

| Option | Description | Default |
| :--- | :--- | :--- |
| `--out PATH` | Where to write the HTML report | `.context/session_summary.html` |
| `--chunk-size N` | Number of prompts per checkpoint batch | `3` |
| `--model NAME` | Model name used in the session (informational only) | — |

> 💡 Increase `--chunk-size` for shorter, simpler sessions. Decrease it if each prompt + response is very long.

### File Structure

```
your-project/
├── .context/
│   ├── session_summary.html    ← The generated report
│   └── logs/                   ← Raw session logs (auto-cleaned)
└── ...

~/.contextmap_update_cache      ← Daily update-check cache (auto-managed)
```

## 🏗️ Architecture

```
ContextMap/
├── bin/
│   ├── contextmap.py       # Core: transcript analysis + HTML generation
│   ├── wrapper.py          # PTY wrapper for transparent session recording
│   └── smart_claude.sh     # Entry point: finds claude + launches wrapper
├── examples/
│   └── example_report.html # Sample output report
└── install.sh              # One-line installer
```

| Component | Role |
| :--- | :--- |
| `smart_claude.sh` | Locates the real `claude` binary, avoids alias loops |
| `wrapper.py` | Records the session using PTY, triggers analysis on exit |
| `contextmap.py` | Parses transcripts, calls LLM, generates/merges HTML reports |

## 🤝 Contributing

Contributions are welcome! If you'd like to improve ContextMap:

1. ⭐ **Star** this repo to show your support
2. 🐛 **Report bugs** via [GitHub Issues](https://github.com/ykai16/ContextMap/issues)
3. 🔀 **Submit PRs** for improvements or new features
4. 💬 **Share feedback** on the report format or visual design

### Development

```bash
# Clone and set up
git clone https://github.com/ykai16/ContextMap.git
cd ContextMap

# Test the Python module
python3 -c "import py_compile; py_compile.compile('bin/contextmap.py', doraise=True)"

# Run the installer locally
./install.sh
```

## 📋 Roadmap

- [x] Transparent session recording via PTY
- [x] LLM-powered HTML report generation
- [x] Multi-session merge and context tracking
- [x] Evolution chain with transition triggers
- [x] Claude Code-inspired visual design
- [x] Checkpoint mechanism for long sessions (v1.1.1)
- [x] Version display on launch + auto-update from GitHub (v1.2.0)
- [ ] Custom prompt templates
- [ ] Multiple LLM provider support (Anthropic, Gemini, local models)
- [ ] VS Code extension for in-editor report viewing
- [ ] Session tagging and search

## 📄 License

Copyright © 2026 [Yan Kai](https://github.com/ykai16). Licensed under the [MIT License](LICENSE).

---

<p align="center">
  <sub>Built with ❤️ for the Claude Code community</sub>
</p>
