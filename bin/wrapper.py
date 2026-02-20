import os
import sys
import pty
import argparse
import datetime
import subprocess
import shutil

def main():
    # 1. Setup paths
    # Assuming this script is in bin/wrapper.py
    # Project root is one level up
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(bin_dir)
    context_dir = os.path.join(os.getcwd(), ".context")
    logs_dir = os.path.join(context_dir, "logs")
    summary_file = os.path.join(context_dir, "session_summary.html")
    
    # Ensure dirs exist
    os.makedirs(logs_dir, exist_ok=True)
    
    # Generate Log Filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"session_{timestamp}.log")
    
    # 2. Find Real Claude
    # We must avoid finding our own wrapper if it's aliased
    # Best bet: check standard paths or ask `which -a` and pick the one that isn't this script
    # For simplicity, we search standard paths or use 'claude' assuming the wrapper calls this script explicitly
    
    real_claude = None
    
    # Priority 1: User specified path
    if os.getenv("REAL_CLAUDE_PATH"):
        real_claude = os.getenv("REAL_CLAUDE_PATH")
        
    # Priority 2: Common install locations
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
    
    # Priority 3: Blind guess (might loop if alias is recursive, but we rely on unalias in shell script)
    if not real_claude:
        real_claude = "claude"

    # 3. Pre-flight Message
    print(f"\033[0;36m🦉 ContextMap active.\033[0m")
    if os.path.exists(summary_file):
        print(f"\n\033[1;33m📜 Previously on this project...\033[0m")
        print("---------------------------------------------------")
        try:
            with open(summary_file, 'r') as f:
                content = f.read()
                # Try to extract content from <section id="anchor">
                if '<section id="anchor">' in content:
                    anchor_part = content.split('<section id="anchor">')[1].split('</section>')[0]
                    # Strip tags to get text
                    import re
                    clean_text = re.sub('<[^<]+?>', '', anchor_part).strip()
                    print(clean_text[:800] + "..." if len(clean_text) > 800 else clean_text)
                elif "# 🧠 Context Anchor" in content:
                    # Legacy markdown support
                    anchor = content.split("# 🧠 Context Anchor")[1].split("#")[0].strip()
                    print(anchor[:500] + "..." if len(anchor) > 500 else anchor)
                else:
                    # Fallback for simple HTML or Markdown
                    import re
                    clean_text = re.sub('<[^<]+?>', '', content).strip()
                    print(clean_text[:200] + "...")
        except Exception:
            pass
        print("---------------------------------------------------\n")

    # 4. Run & Record (The PTY Magic)
    # This works on both Linux and Mac without 'script' quirks
    
    # Prepare arguments
    # sys.argv[0] is this script. sys.argv[1:] are arguments for claude.
    cmd_args = [real_claude] + sys.argv[1:]
    
    # Open log file
    try:
        log_f = open(log_file, 'wb')
        
        def master_read(fd):
            data = os.read(fd, 1024)
            if data:
                log_f.write(data)
                log_f.flush() # Ensure real-time logging
            return data
        
        # Spawn!
        # This blocks until the process exits
        pty.spawn(cmd_args, master_read)
        
    except OSError as e:
        print(f"❌ Error spawning Claude: {e}")
        print(f"   (Tried running: {real_claude})")
        return 1
    finally:
        if 'log_f' in locals():
            log_f.close()

    # 5. Post-flight Analysis
    print(f"\n\n\033[0;32m💾 Session ended. Mapping your journey...\033[0m")
    
    # Call the analyzer (contextmap.py) which is in the same dir as this script
    analyzer_script = os.path.join(bin_dir, "contextmap.py")
    
    # Detect model from args for the analyzer
    model_arg = []
    if "--model" in sys.argv:
        try:
            idx = sys.argv.index("--model")
            model_arg = ["--model", sys.argv[idx+1]]
        except IndexError:
            pass
            
    if os.path.exists(analyzer_script):
        subprocess.run([sys.executable, analyzer_script, log_file, "--out", summary_file] + model_arg)
        if os.path.exists(summary_file):
             print(f"\033[0;36m🗺️  Map Updated! See: {summary_file}\033[0m")
    else:
        print(f"⚠️  Could not find analyzer at {analyzer_script}")

if __name__ == "__main__":
    main()
