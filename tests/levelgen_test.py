#!/usr/bin/env python3
"""B3B-6: generator determinism + invariants over 1000 seeds x depths 1..8."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import levelcheck

if __name__ == "__main__":
    sys.exit(levelcheck.run(1000, 8))
