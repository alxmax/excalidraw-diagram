"""What `gate --risk` says about tests the gate cannot see missing.

RM013 checks a confirmed requirement's cases only once one of them carries a
`# verifies:` tag, so a requirement with none passes in silence: a corpus
measured at 3% of its cases tagged showed a green gate. A `tested-by` line on
a file counts that file as the test of every requirement it names, however
many. And an exemption key left empty exempts nothing yet reads like one.
All three are advice, never a gate finding; the module loads only for
`gate --risk`.
"""
from .acceptance import _automatable_acs
from .healthrows import EXEMPT_KEYS
from .model import _impl_exempt
from .scan import scan_ac_verifies
from .text import _req_file

# A test file that names this many requirements with no case tagged is one
# test standing in for several contracts.
SHARED_TEST_MIN = 3


def case_gaps(reqs, ac_cover):  # implements: REQ-TESTGAPS-1088
    """(rid, missing, total) for every confirmed, non-exempt requirement
    whose automatable cases are not all tagged, most missing first."""
    out = []
    for rid, r in reqs.items():
        m = r["meta"]
        if m.get("status") != "confirmed" or m.get("test_exempt") \
                or _impl_exempt(m):
            continue
        labels = _automatable_acs(r["body"])
        missing = [ac for ac in labels if ac not in ac_cover.get(rid, {})]
        if missing:
            out.append((rid, len(missing), len(labels)))
    return sorted(out, key=lambda g: (-g[1], g[0]))


def shared_test_files(members, ac_cover):  # implements: REQ-TESTGAPS-1088
    """(file, n) for each test file that is the `tested-by` of at least
    SHARED_TEST_MIN requirements and tags none of their cases."""
    claims = {}
    for rid, hits in members.items():
        for role, fp, _line in hits:
            if role == "tested-by":
                claims.setdefault(fp, set()).add(rid)
    tagging = {fp for rid in ac_cover for locs in ac_cover[rid].values()
               for fp, _line in locs}
    return sorted(((fp, len(rids)) for fp, rids in claims.items()
                   if len(rids) >= SHARED_TEST_MIN and fp not in tagging),
                  key=lambda s: (-s[1], s[0]))


def empty_exemptions(reqs):  # implements: REQ-TESTGAPS-1088
    """(rid, key) for each exemption key present with no value."""
    return [(rid, key) for rid in sorted(reqs) for key in EXEMPT_KEYS
            if key in reqs[rid]["meta"] and not reqs[rid]["meta"][key]]


def gap_lines(ws, show_all=False, top_n=3):
    # implements: REQ-TESTGAPS-1088
    """The three buckets as printable lines, or [] when all are empty."""
    cover = ws.ac_cover if ws.ac_cover is not None else (scan_ac_verifies(
        ws.code_root, ws.reqs_dir) if ws.code_root else {})
    cut = (lambda xs: xs) if show_all else (lambda xs: xs[:top_n])
    more = (lambda xs: [] if show_all or len(xs) <= top_n else [
        "  ... {} more — run `reqmap.py gate --risk --all`".format(
            len(xs) - top_n)])
    out = []
    gaps = case_gaps(ws.reqs, cover)
    if gaps:
        out.append("Cases without a test ({})".format(len(gaps)))
        out += ["  {}   {}/{} case(s) carry no `# verifies:` tag   {}".format(
            rid, n, total, _req_file(ws.reqs, rid)) for rid, n, total in cut(gaps)]
        out += more(gaps) + [
            "  -> The gate checks a requirement's cases only once one of them "
            "is tagged. Tag the test of each case `# verifies: <id>#CASE-N`, "
            "or mark a case `verifiable by: inspection`.", ""]
    shared = shared_test_files(ws.members, cover)
    if shared:
        out.append("Shared test files ({})".format(len(shared)))
        out += ["  {}   tested-by of {} requirements, no case tagged".format(
            fp, n) for fp, n in cut(shared)]
        out += more(shared) + [
            "  -> One file stands as the test of several contracts. Tag each "
            "test with the case it checks.", ""]
    empty = empty_exemptions(ws.reqs)
    if empty:
        out.append("Empty exemptions ({})".format(len(empty)))
        out += ["  {}   `{}:` has no value   {}".format(
            rid, key, _req_file(ws.reqs, rid)) for rid, key in cut(empty)]
        out += more(empty) + [
            "  -> An empty key exempts nothing. Delete it, or write the "
            "reason as its value.", ""]
    return out
