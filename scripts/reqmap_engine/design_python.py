"""`ask --design`, Python side: the pillar shapes read through `ast`."""
import ast

from .design import chain_findings, finding_record
from .design import shape_findings

_FN_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
_NESTING_NODES = (ast.If, ast.For, ast.While, ast.With, ast.Try,
                  ast.AsyncFor, ast.AsyncWith)
_SCOPE_NODES = _FN_NODES + (ast.ClassDef,)


def _param_names_of(fn):
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs
            if x.arg not in ("self", "cls")]


def _nesting_depth(node, depth=0):
    """Deepest block nesting under `node`. Iterative on purpose: a generated
    1,000-branch `elif` chain parses fine but sits deeper than the recursion
    limit, and a RecursionError here would kill the whole command."""
    best, stack = depth, [(node, depth)]
    while stack:
        n, d = stack.pop()
        for child in ast.iter_child_nodes(n):
            if isinstance(child, _NESTING_NODES):
                best = max(best, d + 1)
                stack.append((child, d + 1))
            elif not isinstance(child, _SCOPE_NODES):
                stack.append((child, d))
    return best


def _branch_test_kind(test):
    """('type', name) for isinstance(name, ...), ('eq', name) for
    name == <constant>, else None."""
    if (isinstance(test, ast.Call) and isinstance(test.func, ast.Name)
            and test.func.id == "isinstance"
            and test.args and isinstance(test.args[0], ast.Name)):
        return ("type", test.args[0].id)
    if (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and isinstance(test.left, ast.Name)
            and isinstance(test.comparators[0], ast.Constant)):
        return ("eq", test.left.id)
    return None


def _python_records(rel, tree):
    # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951
    """(global-state findings, fn records, class records) for one tree."""
    out, fns, classes = [], [], []
    top = {id(n) for n in tree.body}
    for n in ast.walk(tree):
        if isinstance(n, _FN_NODES):
            names = sorted({g for s in ast.walk(n)
                            if isinstance(s, ast.Global) for g in s.names})
            if names:
                detail = "`{}` writes module state: {}".format(
                    n.name, ", ".join(names))
                out.append(finding_record("global-state", rel, n.lineno,
                                           n.name, detail))
            end = getattr(n, "end_lineno", None) or n.lineno
            fns.append({"name": n.name, "line": n.lineno,
                        "n_lines": end - n.lineno + 1,
                        "depth": _nesting_depth(n),
                        "params": _param_names_of(n), "top": id(n) in top})
        elif isinstance(n, ast.ClassDef):
            bases = {b.id if isinstance(b, ast.Name) else ast.dump(b)
                     for b in n.bases}
            methods = {m.name: ast.dump(m) for m in n.body
                       if isinstance(m, _FN_NODES)}
            classes.append({"name": n.name, "line": n.lineno,
                            "bases": bases, "methods": methods})
    return out, fns, classes


def _python_chains(tree):  # implements: REQ-DESIGN-951
    """Every if/elif chain as (line, tests); an elif is never its own."""
    chains, seen = [], set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.If) or id(n) in seen:
            continue
        tests, node = [], n
        while isinstance(node, ast.If):
            seen.add(id(node))
            t = _branch_test_kind(node.test)
            if t:
                tests.append(t)
            is_elif = (len(node.orelse) == 1
                       and isinstance(node.orelse[0], ast.If))
            node = node.orelse[0] if is_elif else None
        chains.append((n.lineno, tests))
    return chains


def _python_findings(rel, src):
    # implements: REQ-DESIGN-950  # implements: REQ-DESIGN-951
    """The four pillars for one Python file; None when it does not parse."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return None
    out, fns, classes = _python_records(rel, tree)
    out += shape_findings(rel, fns, classes)
    return out + chain_findings(rel, _python_chains(tree))
