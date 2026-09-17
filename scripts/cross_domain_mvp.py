#!/usr/bin/env python3
"""Run the opt-in cross-domain scope MVP. No secrets are accepted on CLI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillopt.cross_domain.experiment import main

if __name__ == "__main__":
    main()
