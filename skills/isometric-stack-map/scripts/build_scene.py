#!/usr/bin/env python3
"""Validate a stack-map scene JSON and inject it into the isometric renderer.

Usage:
  python3 build_scene.py scene.json out.html [--template ../assets/stack-map.html]

The renderer template is never edited; only the JSON inside
<script type="application/json" id="scene-data"> is replaced. Characters that
could close the script element are escaped, so scene strings taken from a repo
cannot inject markup. Exits non-zero with a list of problems when the scene is
invalid or looks like it contains a secret.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KINDS = {
    "service", "frontend", "client", "mobile", "user", "gateway", "cdn", "worker",
    "function", "database", "cache", "storage", "queue", "external", "library", "infra",
}
CLIENT_KINDS = {"client", "mobile", "user"}
STATES = {"on", "idle", "off", "external"}
LINK_KINDS = {"call", "consume", "subscribe"}
MAX_NODES = 80
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

SECRET_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),
    re.compile(r"://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[=:]\s*\S{6,}"),
)
SCENE_RE = re.compile(
    r'(<script type="application/json" id="scene-data">)(.*?)(</script>)', re.DOTALL
)


def strings(value, path="$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{path}[{i}]")


def validate(scene: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(scene, dict):
        return ["scene must be a JSON object"], warnings

    layers = scene.get("layers") or []
    layer_ids = [layer.get("id") for layer in layers if isinstance(layer, dict)]
    if not layer_ids:
        errors.append("layers: at least one layer is required (bottom of the stack first)")
    if len(set(layer_ids)) != len(layer_ids):
        errors.append("layers: ids must be unique")

    nodes = scene.get("nodes") or []
    node_ids: list[str] = []
    for i, node in enumerate(nodes):
        where = f"nodes[{i}]"
        if not isinstance(node, dict) or not node.get("id"):
            errors.append(f"{where}: needs an id")
            continue
        node_ids.append(node["id"])
        if node.get("layer") not in layer_ids:
            errors.append(f"{where} ({node['id']}): unknown layer {node.get('layer')!r}")
        if node.get("kind", "service") not in KINDS:
            errors.append(f"{where} ({node['id']}): kind must be one of {sorted(KINDS)}")
        if node.get("state", "on") not in STATES:
            errors.append(f"{where} ({node['id']}): state must be one of {sorted(STATES)}")
        tags = node.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            errors.append(f"{where} ({node['id']}): tags must be a list of strings")
        if not node.get("cite") and node.get("kind") not in CLIENT_KINDS:
            warnings.append(f"{where} ({node['id']}): no cite — every component should point at the file that proves it")
    if len(set(node_ids)) != len(node_ids):
        errors.append("nodes: ids must be unique")
    if len(node_ids) > MAX_NODES:
        warnings.append(f"{len(node_ids)} nodes — above {MAX_NODES} the map gets unreadable; group or split it")

    known = set(node_ids)
    link_keys = set()
    for i, link in enumerate(scene.get("links") or []):
        where = f"links[{i}]"
        if not isinstance(link, dict):
            errors.append(f"{where}: must be an object")
            continue
        for end in ("from", "to"):
            if link.get(end) not in known:
                errors.append(f"{where}: {end} {link.get(end)!r} is not a node id")
        if link.get("kind", "call") not in LINK_KINDS:
            errors.append(f"{where}: kind must be one of {sorted(LINK_KINDS)}")
        key = (link.get("from"), link.get("to"))
        if key in link_keys:
            errors.append(f"{where}: duplicate link {key[0]} -> {key[1]}; merge the protocols into one")
        link_keys.add(key)

    for i, zone in enumerate(scene.get("zones") or []):
        for member in zone.get("nodes") or []:
            if member not in known:
                errors.append(f"zones[{i}]: member {member!r} is not a node id")

    flow_ids = set()
    for i, flow in enumerate(scene.get("flows") or []):
        if flow.get("id") in flow_ids:
            errors.append(f"flows[{i}]: duplicate id {flow.get('id')!r}")
        flow_ids.add(flow.get("id"))
        if "actor" in flow and flow["actor"] not in known:
            errors.append(f"flows[{i}]: actor {flow['actor']!r} is not a node id")
        if "color" in flow and not COLOR_RE.match(str(flow["color"])):
            errors.append(f"flows[{i}]: color must be a #rrggbb hex value")
        if not flow.get("steps"):
            errors.append(f"flows[{i}]: needs at least one step")
        for j, step in enumerate(flow.get("steps") or []):
            if (step.get("from"), step.get("to")) not in link_keys and (step.get("to"), step.get("from")) not in link_keys:
                errors.append(f"flows[{i}].steps[{j}]: {step.get('from')} -> {step.get('to')} has no matching link")

    for path, text in strings(scene):
        if path.endswith(".url") or path.endswith("repoUrl"):
            if text and not text.startswith("https://"):
                errors.append(f"{path}: only https:// URLs are allowed")
        for pattern in SECRET_RES:
            if pattern.search(text):
                errors.append(f"{path}: looks like a secret or credential — remove it (use the env var name only)")
                break
    return errors, warnings


def inject(template: str, scene: dict) -> str:
    payload = json.dumps(scene, ensure_ascii=False, indent=1)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    out, count = SCENE_RE.subn(lambda m: m.group(1) + "\n" + payload + "\n" + m.group(3), template, count=1)
    if count != 1:
        raise SystemExit("template is missing the scene-data script element")
    return out


def main() -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scene", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--template", type=Path, default=here.parent / "assets" / "stack-map.html")
    args = parser.parse_args()

    try:
        scene = json.loads(args.scene.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: {args.scene}: invalid JSON: {exc}", file=sys.stderr)
        return 1
    errors, warnings = validate(scene)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    args.out.write_text(inject(args.template.read_text(encoding="utf-8"), scene), encoding="utf-8")
    n, l = len(scene.get("nodes") or []), len(scene.get("links") or [])
    print(f"wrote {args.out} — {n} components, {l} links, {len(scene.get('flows') or [])} flows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
