#!/usr/bin/env python3
"""
Initial setup script: create directories, initialize DB, install Playwright browsers.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config_manager import ConfigManager
from src.database.models import Database
from src.utils.logging_config import setup_logging


def main():
    print("=== OpenLinkedIn Initial Setup ===\n")

    # Load config
    config = ConfigManager()
    print(f"Config loaded (provider: {config.ai.provider})")

    # Create directories
    dirs = [
        config.paths.logs,
        os.path.dirname(config.paths.database),
        config.linkedin.browser_profile_dir,
        config.paths.chroma_persist,
        "external",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  Created: {d}")

    # Setup logging
    setup_logging(config.paths.logs)
    print(f"  Logging: {config.paths.logs}/openlinkedin.log")

    # Initialize database
    db = Database(config.paths.database)
    print(f"  Database: {config.paths.database}")

    # Install Playwright browsers
    print("\nInstalling Playwright browsers...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
        print("  Playwright chromium installed")
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: Playwright install failed: {e}")
        print("  Run manually: python -m playwright install chromium")

    # Clone OpenOutreach (if not present)
    oo_path = os.path.join("external", "OpenOutreach")
    if not os.path.isdir(oo_path):
        print("\nCloning OpenOutreach...")
        try:
            subprocess.run(
                [
                    "git",
                    "clone",
                    "https://github.com/eracle/OpenOutreach.git",
                    oo_path,
                ],
                check=True,
            )
            print(f"  Cloned to {oo_path}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"  WARNING: Could not clone OpenOutreach: {e}")
            print("  Browser automation will use fallback implementations")
    else:
        print(f"\n  OpenOutreach already present at {oo_path}")

    print("\n=== Setup Complete ===")
    print("\nNext steps:")
    print("  1. Copy .env.example to .env and fill in your API keys")
    print("  2. Run: python main.py setup")
    print("  3. Run: streamlit run ui/app.py")


if __name__ == "__main__":
    main()
