import os
import sys
import re
import pty
import time
import json
import argparse
import datetime
import subprocess
import shutil
import urllib.request

# ── Update-check constants ────────────────────────────────────────────────────
_CACHE_FILE     = os.path.expanduser("~/.contextmap_update_cache")
_REPO_RAW       = "https://raw.githubusercontent.com/ykai16/ContextMap/master/bin/contextmap.py"
_CHECK_INTERVAL = 86400  # seconds — check at most once per 24 hours

# ── Version helpers ───────────────────────────────────────────────────────────
def _version_tuple(v):
    """Convert '1.2.0' → (1, 2, 0) for reliable comparison."""
    try:
        return tuple(int(x) for x in str(v).split('.'))
    except Exception:
        return (0,)

def _fetch_remote_version(timeout=3):
    """Fetch __version__ from the GitHub raw file. Returns string or None."""
    try:
        with urllib.request.urlopen(_REPO_RAW, timeout=timeout) as resp:
            # Only read first 2 KB — __version__ is always near the top
            content = resp.read(2048).decode('utf-8', errors='replace')
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else None
    except Exception:
        return None

def _load_cache():
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(data):
    try:
        with open(_CACHE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass

def check_and_auto_update(project_root, current_version):
    """Check GitHub for a newer version once per day; auto-update if found."""
    try:
        cache = _load_cache()
        now   = time.time()

        if now - cache.get('last_check', 0) < _CHECK_INTERVAL:
            remote = cache.get('remote_version')   # use cached value — no network call
        else:
            remote = _fetch_remote_version()
            _save_cache({'last_check': now, 'remote_version': remote})

        if not remote:
            return  # network unavailable or parse failed — silent

        if _version_tuple(remote) <= _version_tuple(current_version):
            return  # already up to date

        # New version available → auto-update via git pull
        print(f"\n\033[1;33m⬆  ContextMap v{remote} available — updating...\033[0m")
        result = subprocess.run(
            ["git", "-C", project_root, "pull"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"\033[0;32m✅ Updated to v{remote}. Please restart your terminal to apply.\033[0m\n")
            # Refresh cache timestamp so we don't re-trigger immediately
            _save_cache({'last_check': now, 'remote_version': remote})
        else:
            print(f"\033[0;33m⚠️  Auto-update failed.\033[0m")
            print(f"\033[0;33m   To update manually: cd {project_root} && git pull\033[0m\n")

    except Exception:
        pass  # update check must never break the main session flow

def main():
    # 1. Setup paths
    bin_dir      = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(bin_dir)
    context_dir  = os.path.join(os.getcwd(), ".context")
    logs_dir     = os.path.join(context_dir, "logs")
    summary_file = os.path.join(context_dir, "session_summary.html")

    os.makedirs(logs_dir, exist_ok=True)

    # 2. Import version from contextmap.py (single source of truth)
    try:
        sys.path.insert(0, bin_dir)
        from contextmap import __version__ as CONTEXTMAP_VERSION
    except ImportError:
        CONTEXTMAP_VERSION = "unknown"

    # Generate log filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file  = os.path.join(logs_dir, f"session_{timestamp}.log")

    # 3. Find real Claude binary (avoid alias loops)
    real_claude = None

    if os.getenv("REAL_CLAUDE_PATH"):
        real_claude = os.getenv("REAL_CLAUDE_PATH")

    if not real_claude:
        common_paths = [
            "/usr/local/bin/claude",
            "/opt/homebrew/bin/claude",
            os.path.expanduser("~/.npm-global/bin/claude"),
            os.path.expanduser("~/.nvm/current/bin/claude")
        ]
        for p in common_paths:
            if os.path.exists(p) and os.access(p, os.X_OK):
                real_claude = p
                break

    if not real_claude:
        real_claude = "claude"

    # 4. Launch banner — version number shown on every start
    print(f"\033[0;36m🦉 ContextMap v{CONTEXTMAP_VERSION} active.\033[0m")

    # 5. Auto-update check (once per 24 h, silent on error)
    check_and_auto_update(project_root, CONTEXTMAP_VERSION)

    # 6. "Previously on…" context recap
    if os.path.exists(summary_file):
        print(f"\n\033[1;33m📜 Previously on this project...\033[0m")
        print("---------------------------------------------------")
        try:
            with open(summary_file, 'r') as f:
                content = f.read()
            if '<section id="anchor">' in content:
                anchor_part = content.split('<section id="anchor">')[1].split('</section>')[0]
                clean_text  = re.sub('<[^<]+?>', '', anchor_part).strip()
                print(clean_text[:800] + "..." if len(clean_text) > 800 else clean_text)
            elif "# 🧠 Context Anchor" in content:
                anchor = content.split("# 🧠 Context Anchor")[1].split("#")[0].strip()
                print(anchor[:500] + "..." if len(anchor) > 500 else anchor)
            else:
                clean_text = re.sub('<[^<]+?>', '', content).strip()
                print(clean_text[:200] + "...")
        except Exception:
            pass
        print("---------------------------------------------------\n")

    # 7. Run & Record (PTY magic — transparent passthrough)
    cmd_args = [real_claude] + sys.argv[1:]

    try:
        log_f = open(log_file, 'wb')

        def master_read(fd):
            data = os.read(fd, 1024)
            if data:
                log_f.write(data)
                log_f.flush()
            return data

        pty.spawn(cmd_args, master_read)

    except OSError as e:
        print(f"❌ Error spawning Claude: {e}")
        print(f"   (Tried running: {real_claude})")
        return 1
    finally:
        if 'log_f' in locals():
            log_f.close()

    # 8. Post-session analysis
    print(f"\n\n\033[0;32m💾 Session ended. Mapping your journey...\033[0m")

    analyzer_script = os.path.join(bin_dir, "contextmap.py")

    model_arg = []
    if "--model" in sys.argv:
        try:
            idx = sys.argv.index("--model")
            model_arg = ["--model", sys.argv[idx + 1]]
        except IndexError:
            pass

    if os.path.exists(analyzer_script):
        subprocess.run(
            [sys.executable, analyzer_script, log_file, "--out", summary_file] + model_arg
        )
        if os.path.exists(summary_file):
            print(f"\033[0;36m🗺️  Map Updated! See: {summary_file}\033[0m")
    else:
        print(f"⚠️  Could not find analyzer at {analyzer_script}")

if __name__ == "__main__":
    main()
