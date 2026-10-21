"""apimirage: catch hallucinated and deprecated API usage in Python code.

Strategy: parse the target file with ``ast``, collect every call made through
an imported name, then verify each one for real with ``importlib`` and
``inspect.signature``. Nothing is ever executed -- imports are only used for
existence checks.
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass, field


@dataclass
class Finding:
    kind: str  # ghost-module | ghost-api | ghost-param | deprecated | unverifiable
    file: str
    lineno: int
    name: str
    detail: str

    def one_line(self) -> str:
        return f"{self.file}:{self.lineno}: [{self.kind}] {self.name} -- {self.detail}"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "file": self.file,
            "lineno": self.lineno,
            "name": self.name,
            "detail": self.detail,
        }


@dataclass
class _ImportInfo:
    lineno: int
    dotted: str  # fully qualified dotted name the alias points at


class _UsageCollector(ast.NodeVisitor):
    """Collect import aliases and every call made through an imported name."""

    def __init__(self) -> None:
        self.aliases: dict[str, _ImportInfo] = {}
        self.star_imports: list[_ImportInfo] = []
        self.calls: list[tuple[int, str, list[str], list[str]]] = []
        # (lineno, dotted_name, positional arg count n/a, keyword names)

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            local = a.asname or a.name.split(".")[0]
            self.aliases[local] = _ImportInfo(node.lineno, a.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level > 0 or node.module is None:
            # Relative imports (``from . import x`` / ``from .mod import y``)
            # cannot be resolved to an absolute name without package context,
            # so they are skipped rather than misreported.
            return
        for a in node.names:
            if a.name == "*":
                self.star_imports.append(_ImportInfo(node.lineno, node.module))
                continue
            local = a.asname or a.name
            self.aliases[local] = _ImportInfo(node.lineno, f"{node.module}.{a.name}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = self._resolve_func(node.func)
        if dotted is not None:
            kwargs = [kw.arg for kw in node.keywords if kw.arg is not None]
            has_unpack = any(kw.arg is None for kw in node.keywords)
            self.calls.append((node.lineno, dotted, kwargs, has_unpack))
        self.generic_visit(node)

    def _resolve_func(self, func: ast.expr) -> str | None:
        """Turn `a.b.c(...)` into a dotted name if `a` is an imported alias."""
        parts: list[str] = []
        cur: ast.expr = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        parts.append(cur.id)
        parts.reverse()
        head = parts[0]
        info = self.aliases.get(head)
        if info is None:
            return None
        return ".".join([info.dotted] + parts[1:])


def _deprecation_note(obj: object) -> str | None:
    """Return a deprecation note if the object advertises one, else None."""
    if getattr(obj, "__deprecated__", False):
        return "marked with __deprecated__ (PEP 702)"
    doc = inspect.getdoc(obj)
    if doc:
        first = doc.strip().splitlines()[0]
        if "deprecat" in first.lower():
            return f"docstring says: {first.strip()[:120]}"
    return None


def _verify_dotted(dotted: str) -> tuple[object | None, str | None, str | None]:
    """Import the longest importable prefix of `dotted`, then getattr down.

    Returns (resolved_object, missing_part, error).
    - resolved_object: the final object, or None.
    - missing_part: the dotted name that could not be resolved, or None.
    - error: 'ghost-module' if no prefix imports, 'unverifiable' if the
      import itself blew up, None otherwise.
    """
    parts = dotted.split(".")
    module = None
    rest: list[str] = []
    import_error = False
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        try:
            module = importlib.import_module(prefix)
        except ImportError:
            continue
        except Exception:
            import_error = True
            break
        else:
            rest = parts[i:]
            break
    if module is None:
        return None, dotted, "unverifiable" if import_error else "ghost-module"
    obj: object = module
    resolved = ".".join(parts[: len(parts) - len(rest)])
    for attr in rest:
        try:
            obj = getattr(obj, attr)
        except Exception:
            return None, f"{resolved}.{attr}", None
        resolved = f"{resolved}.{attr}"
    return obj, None, None


def _check_kwargs(obj: object, kwargs: list[str], has_unpack: bool) -> list[str]:
    """Return kwarg names that the callable's signature does not accept."""
    if not kwargs or has_unpack:
        return []
    try:
        sig = inspect.signature(obj)
    except (ValueError, TypeError):
        return []  # builtins without introspectable signatures: skip
    params = sig.parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return []
    accepted = {
        name
        for name, p in params.items()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    return [k for k in kwargs if k not in accepted]


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings


def check_source(source: str, filename: str = "<string>") -> ScanResult:
    """Scan Python source code and return findings. Never executes the code."""
    result = ScanResult()
    tree = ast.parse(source, filename=filename)
    collector = _UsageCollector()
    collector.visit(tree)

    ghost_roots: set[str] = set()

    # Pass 1: verify the imports themselves.
    for local, info in collector.aliases.items():
        obj, missing, error = _verify_dotted(info.dotted)
        if error == "ghost-module":
            result.findings.append(
                Finding(
                    "ghost-module", filename, info.lineno, info.dotted,
                    "module cannot be imported -- possibly hallucinated",
                )
            )
            ghost_roots.add(info.dotted.split(".")[0])
        elif error == "unverifiable":
            result.findings.append(
                Finding(
                    "unverifiable", filename, info.lineno, info.dotted,
                    "import raised an unexpected error; could not verify",
                )
            )
        elif missing:
            result.findings.append(
                Finding(
                    "ghost-api", filename, info.lineno, missing,
                    f"module '{info.dotted.rsplit('.', 1)[0] if '.' in missing else info.dotted}' "
                    "imports, but this attribute does not exist -- possibly hallucinated",
                )
            )
        elif obj is not None:
            note = _deprecation_note(obj)
            if note:
                result.findings.append(
                    Finding("deprecated", filename, info.lineno, info.dotted,
                            f"imported name is deprecated: {note}")
                )

    # Pass 2: verify every call made through an imported name.
    for lineno, dotted, kwargs, has_unpack in collector.calls:
        if dotted.split(".")[0] in ghost_roots:
            continue  # already reported at the import site
        obj, missing, error = _verify_dotted(dotted)
        if error == "ghost-module":
            continue  # import site already reported
        if error == "unverifiable":
            result.findings.append(
                Finding("unverifiable", filename, lineno, dotted,
                        "import raised an unexpected error; could not verify")
            )
            continue
        if missing:
            result.findings.append(
                Finding("ghost-api", filename, lineno, missing,
                        "attribute does not exist on the real module -- possibly hallucinated")
            )
            continue
        note = _deprecation_note(obj)
        if note:
            result.findings.append(
                Finding("deprecated", filename, lineno, dotted,
                        f"API is deprecated: {note}")
            )
        bad_kwargs = _check_kwargs(obj, kwargs, has_unpack)
        for kw in bad_kwargs:
            result.findings.append(
                Finding("ghost-param", filename, lineno, f"{dotted}({kw}=...)",
                        f"keyword argument '{kw}' is not accepted by the real signature")
            )

    result.findings.sort(key=lambda f: (f.lineno, f.kind))
    return result


def check_file(path: str) -> ScanResult:
    with open(path, "r", encoding="utf-8") as f:
        return check_source(f.read(), filename=path)


__all__ = ["Finding", "ScanResult", "check_source", "check_file"]
