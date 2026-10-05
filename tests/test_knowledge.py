import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts import okf


class KnowledgeBundleTests(unittest.TestCase):
    def test_docs_bundle_conforms_to_okf(self):
        self.assertEqual(okf.check(), [])

    def test_check_reports_nonconforming_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "good.md").write_text("---\ntype: Runbook\ngenerated:\n  by: human:someone\n  at: 2026-10-05T00:00:00Z\n---\n# Good\n")
            (root / "bare.md").write_text("# No frontmatter\n")
            (root / "loose.md").write_text("---\ntype: Runbook\nstatus: final\ngenerated:\n  by: process:report\n  at: 2026-10-05\n"
                                           "verified: {by: someone}\nsources:\n- resource: missing.json\n---\n# Loose\n")
            (root / "log.md").write_text("# Log\n\n## 2026-09-01\n* Older.\n\n## 2026-10-01\n* Newer.\n")
            self.assertEqual(okf.check(root, {}), [
                "bare.md: no parseable YAML frontmatter",
                "loose.md: `status` must be one of ['deprecated', 'draft', 'stable']",
                "loose.md: `generated.at` must be an ISO 8601 datetime with a UTC offset",
                "loose.md: each `verified` entry needs an actor `by` and an `at` with a UTC offset",
                "loose.md: source missing.json does not exist",
                "index.md is missing or out of date; run python scripts/okf.py index",
                "log.md: dates must run newest first"])
            (root / "index.md").write_text(okf.render_index(root, {}))
            self.assertNotIn("index.md is missing or out of date; run python scripts/okf.py index", okf.check(root, {}))

    def test_frozen_protocols_are_pinned_by_recorded_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            protocol = root / "protocol.md"
            protocol.write_bytes(b"# Protocol\n\nFixed before scoring.\n")
            (root / "results.json").write_text(json.dumps({"protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest()}))
            protocol.write_bytes(b"# Protocol\n\nFixed before scoring.\n\n## Amendment\n")
            for mode, expected in (("prefix", []), ("whole", ["protocol.md: SHA-256 no longer matches protocol_sha256 in results.json"])):
                frozen = {"protocol.md": ("results.json", mode, "A protocol.")}
                (root / "index.md").write_text(okf.render_index(root, frozen))
                self.assertEqual(okf.check(root, frozen), expected)

    def test_write_concept_keeps_frontmatter_and_restamps_generated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.md"
            path.write_text("---\ntype: Validation Report\ntags: [m5]\n---\n\n# Old\n", encoding="utf-8")
            okf.write_concept(path, "# New\n", "process:report")
            meta, body = okf.split(path.read_text(encoding="utf-8"))
            self.assertEqual((meta["type"], meta["tags"], meta["generated"]["by"], body),
                             ("Validation Report", ["m5"], "process:report", "# New\n"))
            self.assertIsNotNone(meta["generated"]["at"].tzinfo)
            plain = Path(folder) / "plain.md"
            okf.write_concept(plain, "# Plain\n", "process:report")
            self.assertEqual(plain.read_text(encoding="utf-8"), "# Plain\n")


if __name__ == "__main__":
    unittest.main()
