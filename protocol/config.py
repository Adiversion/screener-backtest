"""Protocol config: load the versioned YAML and expose a stable hash.

The hash is computed over the canonical JSON form (sorted keys, compact
separators) so it is independent of YAML formatting/comments. Every report
embeds it; the validation run refuses to proceed on a hash mismatch.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "protocol_v2.yaml"
_HASH_STATE = Path(__file__).resolve().parent.parent / ".protocol_state.json"


def canonical_hash(cfg: dict[str, Any]) -> str:
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(p, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    cfg["_source"] = str(p)
    cfg["_hash"] = canonical_hash({k: v for k, v in cfg.items() if not k.startswith("_")})
    return cfg


def get(cfg: dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def record_discovery_hash(cfg_hash: str) -> None:
    _HASH_STATE.write_text(json.dumps({"discovery_hash": cfg_hash}), encoding="utf-8")


def last_discovery_hash() -> str | None:
    if not _HASH_STATE.exists():
        return None
    try:
        return json.loads(_HASH_STATE.read_text(encoding="utf-8")).get("discovery_hash")
    except (json.JSONDecodeError, OSError):
        return None


def assert_validation_gate(cfg: dict[str, Any], exploratory: bool) -> None:
    """Rule 3: validation must not run on a config newer than discovery."""
    if exploratory:
        return
    prior = last_discovery_hash()
    if prior is not None and prior != cfg["_hash"]:
        raise SystemExit(
            "Config hash changed since the last discovery run "
            f"({prior[:12]} -> {cfg['_hash'][:12]}).\n"
            "Re-run discovery, or pass --exploratory to watermark outputs."
        )
