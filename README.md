# 🗺️ Context Cartographer for Claude Code

**Stop "Context Rot".** This tool automatically maps your coding journey, summarizing your intents and decisions every time you close a session, and reloading your memory when you return.

## 🚀 Installation

One-line install (assuming you have `git` and `python3`):

```bash
git clone https://github.com/ykai16/context-cartographer.git
cd context-cartographer
./install.sh
```

Then, restart your terminal or run `source ~/.zshrc`.

## 🧠 How it Works

It wraps your `claude` command with a smart layer:

1.  **On Start**: Checks `.context/session_summary.md` and displays a "Previously on..." summary.
2.  **During Session**: Records your interaction (transparently) using `script`.
3.  **On Exit**: Automatically analyzes the logs using GPT-4o (or compatible LLM) to generate a structured report.

## ⚙️ Configuration

You must set your LLM API Key in your shell profile (`.zshrc` / `.bashrc`):

```bash
export OPENAI_API_KEY="sk-..."
# Or if you use Anthropic directly in the python script (requires code tweak):
# export ANTHROPIC_API_KEY="sk-ant-..."
```

## 📂 Output Example

Check `.context/session_summary.md` in your project root:

```markdown
# 🗺️ Session Evolution
[Mermaid Graph ...]

# 📝 Key Decisions Log
| Time | Intent | Action | Outcome |
| :--- | :--- | :--- | :--- |
| 10:00 | Fix Bug | Modified parser.py | Success |

# 🧠 Context Anchor
We left off refactoring the AsyncIO loop...
```

---
*Built by Yancy (OpenClaw AI).*
