#!/usr/bin/env python3
"""启动 CSI Web 控制台。

用法:
    python scripts/webui.py [--port 8000]
然后浏览器打开 http://127.0.0.1:8000
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from espectre_csi.webapp import main  # noqa: E402

if __name__ == "__main__":
    main()
