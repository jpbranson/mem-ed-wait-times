import re
import unittest
from pathlib import Path
from unittest.mock import patch

from edwait.data import History


class DashboardTests(unittest.TestCase):
    def test_empty_history_keeps_registry_and_explicit_missing_message(self):
        # Exercise every executable cell, including both empty history views.
        source = Path("dashboard/index.qmd").read_text(encoding="utf-8")
        cells = re.findall(r"```\{python\}\n(.*?)\n```", source, re.DOTALL)
        self.assertEqual(len(cells), 5)
        namespace = {}
        with patch("pathlib.Path.exists", return_value=False), patch("IPython.display.display") as display:
            for cell in cells:
                exec(compile(cell, "dashboard/index.qmd", "exec"), namespace)
        html = "\n".join(str(call.args[0].data) for call in display.call_args_list)
        self.assertIn("No valid historical observations", html)
        self.assertIn("All-hospital history is unavailable", html)
        self.assertIn('id="facility-registry"', html)
        self.assertEqual(len(namespace["facilities"]), 20)
        self.assertIsNone(namespace["context"])
        self.assertIn('id="hospital-select"', html)


if __name__ == "__main__":
    unittest.main()
