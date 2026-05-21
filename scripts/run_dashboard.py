#!/usr/bin/env python3
"""Launch the Hevy training dashboard.

Usage:
    python scripts/run_dashboard.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
APP_PATH = _PROJECT_ROOT / "hevy" / "dashboard" / "app.py"

if not APP_PATH.exists():
    print(f"❌ Dashboard app not found at {APP_PATH}")
    sys.exit(1)

print("🚀 Launching Hevy Training Dashboard...")
print(f"   Streamlit app: {APP_PATH}")
print(f"   Working dir:   {_PROJECT_ROOT}")
print()

cmd = [
    sys.executable, "-m", "streamlit", "run",
    str(APP_PATH),
    "--",  # end of streamlit options
]

subprocess.run(cmd, cwd=str(_PROJECT_ROOT))
