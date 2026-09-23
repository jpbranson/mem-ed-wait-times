import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from edwait.data import registry
from edwait.latest import build_latest
from edwait.prepare import build_comparisons
from edwait.data import History, timestamp
from tests.fakes import attempt, record


class ContractTests(unittest.TestCase):
    def test_comparison_artifact_schema_and_support_nulls(self):
        schema = json.loads(Path("docs/comparisons.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        artifact = build_comparisons(History(records=[record()]), timestamp("2026-09-14T01:00:00Z"), facilities=[{"slug":"memphis"}])
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(artifact)
        self.assertIsNone(artifact["facilities"][0]["history"][0][2])
        artifact["facilities"][0]["history"][0][8] = 1.5
        self.assertTrue(list(validator.iter_errors(artifact)))

    def test_latest_and_embedded_raw_contract(self):
        raw = json.loads(Path("docs/ed-wait.schema.json").read_text())
        latest = json.loads(Path("docs/latest.schema.json").read_text())
        schemas = Registry().with_resource(raw["$id"], Resource.from_contents(raw))
        validator = Draft202012Validator(latest, registry=schemas, format_checker=FormatChecker())
        Draft202012Validator.check_schema(raw)
        Draft202012Validator.check_schema(latest)
        artifact = build_latest(None, [record()], {"memphis": attempt(), "desoto": attempt(state="failed")},
                                registry(), generated_at="2026-09-14T01:00:00Z")
        validator.validate(artifact)
        validator.validate(build_latest(None, [], {}, registry(), generated_at="2026-09-14T01:00:00Z"))
        artifact["facilities"][0]["last_attempt"] = {"state": "failed"}
        self.assertTrue(list(validator.iter_errors(artifact)))


if __name__ == "__main__":
    unittest.main()
