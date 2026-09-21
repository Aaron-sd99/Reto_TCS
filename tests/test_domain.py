import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "transaction-service"))

from app.domain import ordered_account_locks


class DomainTests(unittest.TestCase):
    def test_account_locks_are_deterministic(self):
        self.assertEqual(
            ordered_account_locks("ACC-2001", "ACC-1001"),
            ordered_account_locks("ACC-1001", "ACC-2001"),
        )


if __name__ == "__main__":
    unittest.main()
