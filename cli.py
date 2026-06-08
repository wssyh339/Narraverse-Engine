from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app.cli.main import main


if __name__ == "__main__":
    if "--input" in sys.argv and "--output" in sys.argv and len(sys.argv) > 1 and sys.argv[1].startswith("--"):
        sys.argv.insert(1, "canon-run")
    main()
