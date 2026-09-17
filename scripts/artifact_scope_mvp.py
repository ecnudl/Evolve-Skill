#!/usr/bin/env python3
"""Run the opt-in artifact-scope experiment without modifying the frozen v1."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillopt.scope_evolution_v2.experiment import main

if __name__ == "__main__":
    main()
