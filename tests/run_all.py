"""全部のテストを回す。失敗があれば終了コード 1。

    python tests/run_all.py
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(HERE), top_level_dir=str(HERE))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
