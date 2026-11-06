"""The translation cache (`_i18n/<locale>.json`), read-only: hashes, and
attaching the entries still fresh to the map's nodes so the viewer can
show them.
"""
import hashlib, json, os

from . import config as cfg
from .sections import ACCEPTANCE_LABELS, CONTRACT_LABELS, _from_any
from .text import _first_quote, _section_raw, _title


# ---------------------------------------------------------------------------
# Content translation, reading half — implements: ARCH-TRANSLATE-044
#
# READ-ONLY. The command that produced `requirements/_i18n/<locale>.json` was
# removed on 2026-09-05, together with everything that shelled out to an
# external LLM CLI. What is left reads an already-committed cache file, so no
# code path in this engine starts a subprocess and the gate/sync/CI path stays
# usable on a machine that has never heard of `claude`. A cache entry is served
# only while its hash matches the requirement, so the cache decays as
# requirements are edited and refreshing it is a manual step. Since v8.2.0
# (ADR-0047) nothing measures that decay either: `ask --i18n`, RM029 and
# LANGUAGE are gone.
# ---------------------------------------------------------------------------
# part of the cache key: bump to invalidate every cached
TRANSLATOR_VERSION = "1"


def _translation_source_text(body, title):  # implements: ARCH-TRANSLATE-044
    """The exact span that gets translated and hashed: title + WHY + Contract +
    Acceptance. Deliberately wider than binding_hash() (Contract+Acceptance
    only) — a title-only edit must also invalidate a cached translation."""
    return "\n".join([
        title, _first_quote(body),
        _from_any(_section_raw, body, CONTRACT_LABELS),
        _from_any(_section_raw, body, ACCEPTANCE_LABELS),
    ])


def translation_hash(body, title):
    # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-937
    """Cache-invalidation key for one requirement's translation. NOT
    binding_hash() — see _translation_source_text. Includes
    TRANSLATOR_VERSION so bumping the prompt or the model invalidates
    every cached entry in one step, not file-by-file."""
    h = hashlib.sha256()
    h.update(_translation_source_text(body, title).encode("utf-8"))
    h.update(TRANSLATOR_VERSION.encode("utf-8"))
    return h.hexdigest()[:12]


def _load_translations(reqs, reqs_dir):
    # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-938
    """Read every requirements/_i18n/<locale>.json cache file and return
    {rid: {locale: {title, intent, contract, acceptance}}} for entries whose
    stored hash still matches the requirement's CURRENT content. A stale entry
    (source edited since the last `translate` run) is silently dropped rather
    than served — this is what keeps `map`/`map --check` deterministic and
    `claude`-free: they only ever read a file already sitting on disk, and they
    never serve a translation known to be out of date."""
    i18n_dir = os.path.join(reqs_dir, "_i18n")
    if not os.path.isdir(i18n_dir):
        return {}
    out = {}
    for fname in sorted(os.listdir(i18n_dir)):
        if not fname.endswith(".json"):
            continue
        locale = fname[:-len(".json")]
        if "*" not in cfg.MAP_LOCALES and locale not in cfg.MAP_LOCALES:
            continue
        try:
            with open(os.path.join(i18n_dir, fname), encoding="utf-8") as f:
                cache = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(cache, dict):
            continue
        for rid, entry in cache.items():
            r = reqs.get(rid)
            if not r or not isinstance(entry, dict):
                continue
            title = _title(r["body"])
            if entry.get("hash") != translation_hash(r["body"], title):
                continue
            out.setdefault(rid, {})[locale] = {
                k: entry.get(k, "") for k in (
                    "title", "intent", "contract", "acceptance"
                )
            }
    return out


def _attach_translations(data, reqs, reqs_dir):
    # implements: ARCH-TRANSLATE-044  # implements: REQ-TRANSLATE-938
    """Mutate data['nodes'] in place, adding node['i18n'] = {locale: {...}} for
    any node with a fresh cached translation. Shared by cmd_map
    so both emit the same graph — no `claude` call here, file reads only."""
    i18n = _load_translations(reqs, reqs_dir)
    for node in data["nodes"]:
        if node["id"] in i18n:
            node["i18n"] = i18n[node["id"]]
    return data
