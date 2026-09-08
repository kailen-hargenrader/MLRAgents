"""Comparing two configuration cells.

An ablation is a claim that exactly one thing changed. That claim is usually
made in prose and checked by eye, which is how a grid ends up differing in two
places and the paper attributes the whole effect to one of them. `diff` turns
the claim into a structural comparison, and `verdict` turns it into a decision.

Configs are compared as flattened key/value maps rather than as text, so that
key order, indentation and comments cannot manufacture a difference, and a
value nested three levels down cannot hide one.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUFFIXES = {".yaml", ".yml", ".json", ".toml"}


class UnsupportedConfig(ValueError):
    """A config file this module cannot parse structurally."""


def load(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        raise UnsupportedConfig(
            f"{path} has suffix {suffix or '(none)'}; "
            f"expected one of {', '.join(sorted(SUFFIXES))}"
        )
    text = path.read_text()
    if suffix == ".json":
        return json.loads(text)
    if suffix == ".toml":
        return tomllib.loads(text)
    import yaml

    return yaml.safe_load(text)


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    """Collapse nested mappings and sequences to dotted keys.

    Sequence elements are indexed (`defaults[0]`) rather than compared as a
    whole, so a diff points at the element that changed instead of at the list.
    """
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(value, child))
        return out
    if isinstance(data, (list, tuple)):
        out = {}
        for index, value in enumerate(data):
            out.update(flatten(value, f"{prefix}[{index}]"))
        return out
    return {prefix: data}


@dataclass
class Difference:
    key: str
    left: Any = None
    right: Any = None
    present_in: str = "both"


@dataclass
class Diff:
    left: str
    right: str
    differences: list[Difference] = field(default_factory=list)

    @property
    def keys(self) -> list[str]:
        return [d.key for d in self.differences]


_MISSING = object()


def diff(left_path: Path, right_path: Path) -> Diff:
    left = flatten(load(Path(left_path)))
    right = flatten(load(Path(right_path)))
    differences = []
    for key in sorted(set(left) | set(right)):
        a = left.get(key, _MISSING)
        b = right.get(key, _MISSING)
        if a is _MISSING:
            differences.append(Difference(key, None, b, "right"))
        elif b is _MISSING:
            differences.append(Difference(key, a, None, "left"))
        elif a != b:
            differences.append(Difference(key, a, b, "both"))
    return Diff(str(left_path), str(right_path), differences)


def under_axis(key: str, axis: str) -> bool:
    """Whether `key` is the axis or nested beneath it.

    Prefix matching is on key boundaries, so an axis of `model.kernel` does not
    silently absorb `model.kernel_scale`.
    """
    return key == axis or key.startswith(f"{axis}.") or key.startswith(f"{axis}[")


def verdict(result: Diff, axes: list[str] | str | None) -> dict:
    """Whether the diff is confined to the declared axes.

    With no axes the diff is reported and nothing is judged; a caller who has
    not said what was supposed to change cannot be told it changed.
    """
    listed = [axes] if isinstance(axes, str) else list(axes or ())
    payload = {
        "left": result.left,
        "right": result.right,
        "axes": listed,
        "differing_keys": result.keys,
        "differences": [
            {
                "key": d.key,
                "left": d.left,
                "right": d.right,
                "present_in": d.present_in,
            }
            for d in result.differences
        ],
    }
    if not listed:
        payload["ok"] = None
        payload["summary"] = (
            f"{len(result.differences)} key(s) differ; no axis declared, so "
            "nothing was checked. Pass axes to assert what was supposed to change."
        )
        return payload

    violations = [
        d.key
        for d in result.differences
        if not any(under_axis(d.key, axis) for axis in listed)
    ]
    unchanged = [
        axis
        for axis in listed
        if not any(under_axis(key, axis) for key in result.keys)
    ]
    payload["violations"] = violations
    payload["axes_that_did_not_change"] = unchanged
    payload["ok"] = not violations and not unchanged
    if violations:
        payload["summary"] = (
            f"{len(violations)} key(s) differ outside the declared axes: "
            f"{', '.join(violations[:8])}. These two cells do not isolate "
            f"{', '.join(listed)}."
        )
    elif unchanged:
        payload["summary"] = (
            f"the declared axis {', '.join(unchanged)} is identical in both "
            "cells; this pair is not an ablation of it."
        )
    else:
        payload["summary"] = (
            f"the only differences are under {', '.join(listed)}; this pair "
            "isolates the declared axis."
        )
    return payload
