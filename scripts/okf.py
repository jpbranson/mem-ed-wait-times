"""Open Knowledge Format (OKF v0.2) tooling for the docs/ knowledge bundle.

    python scripts/okf.py check   # list conformance problems; exit 1 if any
    python scripts/okf.py index   # rewrite docs/index.md from concept frontmatter, then check

Specification: https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import yaml

BUNDLE = Path(__file__).resolve().parents[1] / "docs"
OKF_VERSION = "0.2"
RESERVED = {"index.md", "log.md"}
STATUSES = {"draft", "stable", "deprecated"}
ACTOR = re.compile(r"(human|process):\S+|[^\s:/]+/\S+")
# Pre-registered protocols whose committed (LF) bytes are pinned by protocol_sha256 in study
# evidence, so they cannot carry frontmatter. "prefix": an amendment was appended after the
# recorded hash, which covers the text frozen before it.
FROZEN = {
    "m2-benefit-protocol.md": ("m2-benefit-results.json", "whole",
        "Candidate rules, metrics and selection plan, committed before any real-data scoring, for when an "
        "alternative's drive-plus-published-wait estimate may be called meaningfully lower."),
    "m3-relationship-protocol.md": ("m3-relationship-results.json", "whole",
        "Inputs, periods, neighbor groups, statistics and confirmation rules fixed before computing any "
        "pair statistic among published readings."),
    "m5-study-protocol.md": ("m5-study-manifest.json", "prefix",
        "Frozen inputs, time policy, chronological phases and provisional release gates for the offline "
        "forecasting study, with an amendment appended before calibration scoring."),
}
# index.md sections in order, each with the concept types it lists.
SECTIONS = [
    ("Plan", {"Development Plan"}),
    ("Operations", {"Runbook", "Data Collector"}),
    ("Data contracts", {"Data Contract"}),
    ("Validation reports", {"Validation Report"}),
    ("Frozen study protocols", set()),
    ("Deployment records", {"Deployment Record"}),
    ("Research records", {"Research Record"}),
    ("Work logs and drafts", {"Work Log", "Correspondence Draft"}),
    ("Other", set()),
]


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(datetime, lambda dumper, value: dumper.represent_scalar(
    "tag:yaml.org,2002:timestamp", value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
_Dumper.add_representer(list, lambda dumper, value: dumper.represent_sequence(
    "tag:yaml.org,2002:seq", value, flow_style=all(isinstance(item, str) for item in value)))


def dump(meta):
    """Frontmatter block: block mappings, string lists in flow style, timestamps in UTC."""
    return "---\n" + yaml.dump(meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                               default_flow_style=False, width=1 << 16) + "---\n"


def split(text):
    """Return (frontmatter mapping or None, body) for a markdown document."""
    match = re.match(r"---\n(.*?)^---\n", text, re.S | re.M)
    if not match:
        return None, text
    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, text
    return (meta if isinstance(meta, dict) else None), text[match.end():].lstrip("\n")


def write_concept(path, body, by):
    """Write a generated document, keeping its existing frontmatter and restamping `generated`."""
    path = Path(path)
    meta = split(path.read_text(encoding="utf-8"))[0] if path.exists() else None
    if meta is not None:
        meta["generated"] = {"by": by, "at": datetime.now(timezone.utc).replace(microsecond=0)}
        body = dump(meta) + "\n" + body
    path.write_text(body, encoding="utf-8")


def _instant(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    return isinstance(value, datetime) and value.tzinfo is not None


def _check_meta(meta, root, folder):
    if not isinstance(meta.get("type"), str) or not meta["type"].strip():
        yield "`type` must be a non-empty string"
    if meta.get("status", "stable") not in STATUSES:
        yield f"`status` must be one of {sorted(STATUSES)}"
    generated = meta.get("generated")
    if generated is not None:
        if not isinstance(generated, dict) or not ACTOR.fullmatch(str(generated.get("by", ""))):
            yield "`generated.by` must be an actor: human:<id>, process:<id> or <producer>/<version>"
        elif "at" in generated and not _instant(generated["at"]):
            yield "`generated.at` must be an ISO 8601 datetime with a UTC offset"
    verified = meta.get("verified", [])
    for event in [verified] if isinstance(verified, dict) else verified:
        if not isinstance(event, dict) or not ACTOR.fullmatch(str(event.get("by", ""))) or not _instant(event.get("at")):
            yield "each `verified` entry needs an actor `by` and an `at` with a UTC offset"
    if "stale_after" in meta and not _instant(meta["stale_after"]):
        yield "`stale_after` must be an ISO 8601 datetime with a UTC offset"
    for source in meta.get("sources", []):
        resource = source.get("resource") if isinstance(source, dict) else None
        if not resource:
            yield "every `sources` entry needs a `resource`"
        elif "://" not in resource and " " not in resource:
            target = root / resource[1:] if resource.startswith("/") else folder / resource
            if not target.exists():
                yield f"source {resource} does not exist"


def _check_frozen(root, name, evidence, mode):
    path = root / name
    if not path.exists():
        yield f"{name}: frozen protocol is missing"
        return
    recorded = json.loads((root / evidence).read_text(encoding="utf-8"))["protocol_sha256"]
    data = path.read_bytes().replace(b"\r\n", b"\n")
    ends = [len(data)] if mode == "whole" else [i + 1 for i, byte in enumerate(data) if byte == 10]
    if not any(hashlib.sha256(data[:end]).hexdigest() == recorded for end in ends):
        yield f"{name}: SHA-256 no longer matches protocol_sha256 in {evidence}"


def _check_reserved(root, frozen):
    index = root / "index.md"
    if not index.exists() or index.read_text(encoding="utf-8") != render_index(root, frozen):
        yield "index.md is missing or out of date; run python scripts/okf.py index"
    for path in root.rglob("*.md"):
        if path.name not in RESERVED:
            continue
        meta, body = split(path.read_text(encoding="utf-8"))
        name = path.relative_to(root).as_posix()
        if meta is not None and (path != index or set(meta) != {"okf_version"}):
            yield f"{name}: only the bundle-root index.md may carry frontmatter, and only okf_version"
        if path.name == "log.md":
            dates = re.findall(r"^## (.+)$", body, re.M)
            if not all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates):
                yield f"{name}: date headings must be YYYY-MM-DD"
            elif dates != sorted(dates, reverse=True):
                yield f"{name}: dates must run newest first"


def check(root=BUNDLE, frozen=FROZEN):
    """Return the OKF conformance problems in the bundle at `root`; frozen protocols are checked by hash."""
    problems = []
    for name, (evidence, mode, _) in frozen.items():
        problems += _check_frozen(root, name, evidence, mode)
    for path in sorted(root.rglob("*.md")):
        name = path.relative_to(root).as_posix()
        if path.name in RESERVED or name in frozen:
            continue
        meta = split(path.read_text(encoding="utf-8"))[0]
        if meta is None:
            problems.append(f"{name}: no parseable YAML frontmatter")
        else:
            problems += [f"{name}: {problem}" for problem in _check_meta(meta, root, path.parent)]
    return problems + list(_check_reserved(root, frozen))


def render_index(root=BUNDLE, frozen=FROZEN):
    """Bundle-root index.md: concepts grouped by type, each entry carrying its description."""
    entries = {section: [] for section, _ in SECTIONS}
    for path in sorted(root.rglob("*.md")):
        name = path.relative_to(root).as_posix()
        if path.name in RESERVED:
            continue
        text = path.read_text(encoding="utf-8")
        if name in frozen:
            evidence, _, description = frozen[name]
            title = re.search(r"^# (.+)$", text, re.M).group(1)
            entries["Frozen study protocols"].append(
                f"* [{title}]({name}) - {description} Not editable: its SHA-256 is recorded in [{evidence}]({evidence}).")
            continue
        meta = split(text)[0] or {}
        section = next((s for s, types in SECTIONS if meta.get("type") in types), "Other")
        status = meta.get("status", "stable")
        entries[section].append(f"* [{meta.get('title') or path.stem}]({name}) - {meta.get('description', '')}"
                                + ("" if status == "stable" else f" ({status})"))
    for path in sorted(root.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        summary = schema.get("description", "").split(". ")[0].rstrip(".")
        entries["Data contracts"].append(f"* [{schema['title']}]({path.name}) - JSON Schema" + (f": {summary}." if summary else "."))
    lines = ["---", f'okf_version: "{OKF_VERSION}"', "---", "",
             "# About this bundle", "",
             "* [Update log](log.md) - Creations, deprecations and structural changes to this bundle, newest first.",
             "* [Bundle tooling](../scripts/okf.py) - Generates this index and checks conformance "
             "(`python scripts/okf.py index`).", ""]
    for section, _ in SECTIONS:
        if entries[section]:
            lines += [f"# {section}", "", *entries[section], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=("check", "index"), default="check")
    if parser.parse_args().command == "index":
        (BUNDLE / "index.md").write_text(render_index(), encoding="utf-8")
    problems = check()
    print("\n".join(problems) or f"OKF {OKF_VERSION} bundle conforms: {BUNDLE}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
