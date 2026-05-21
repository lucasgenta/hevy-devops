#!/usr/bin/env python3
"""PWA-enabled dashboard launcher for Android.

Serves:
  - PWA static files (manifest.json, sw.js, icons) from pwa/
  - Streamlit dashboard on port 8501

This wraps Streamlit to inject PWA support via a lightweight HTTP server.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent

STREAMLIT_PORT = 8501
PWA_DIR = _PROJECT_ROOT / "pwa"


def main() -> None:
    """Launch the dashboard with PWA headers injected."""
    app_path = _PROJECT_ROOT / "hevy" / "dashboard" / "app.py"

    if not app_path.exists():
        print(f"❌ Dashboard not found at {app_path}")
        sys.exit(1)

    if not PWA_DIR.exists():
        print(f"⚠️  PWA directory not found at {PWA_DIR}")
        print("   Continuing without PWA support...")

    print("🚀 Launching Hevy Dashboard with PWA support...")
    print(f"   App:        {app_path}")
    print(f"   Port:       {STREAMLIT_PORT}")
    print(f"   PWA dir:    {PWA_DIR}")
    print()
    print(f"   📱 Open on Android: http://YOUR_SERVER_IP:{STREAMLIT_PORT}")
    print(f"   📱 Install as app:  Chrome menu → 'Add to Home screen'")
    print()

    # Streamlit will auto-detect files in the working directory's static folder
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
        "--",
    ]

    subprocess.run(cmd, cwd=str(_PROJECT_ROOT))


if __name__ == "__main__":
    main()
