# ghostapi

LLMs use deprecated APIs up to 38% of the time — and ruff can't catch it.

`ghostapi` is a tiny static checker that finds **hallucinated** and
**deprecated** API usage in Python code. It parses your file with `ast`,
collects every call made through an imported name, then verifies each one
**for real** with `importlib` + `inspect.signature`. Nothing is ever executed —
imports are only used for existence checks.

```bash
$ ghostapi app.py
app.py:12: [ghost-api] requests.post_json -- attribute does not exist on the real module -- possibly hallucinated
app.py:27: [ghost-param] json.dumps(pretty=...) -- keyword argument 'pretty' is not accepted by the real signature
app.py:41: [deprecated] asyncio.coroutine -- API is deprecated: marked with __deprecated__ (PEP 702)
ghostapi: 3 findings in 1 file
```

Zero dependencies. Python standard library only (`ast` + `importlib` + `inspect`).
Everything stays local.

## Install

```bash
pip install ghostapi
```

Or from source:

```bash
git clone https://github.com/hahahahahahahahah6/ghostapi
cd ghostapi
pip install .
```

## Usage

```bash
ghostapi file.py [more_files.py ...]
ghostapi -f json src/ --quiet
ghostapi --version
```

Exit codes: `0` = clean, `1` = findings, `2` = usage error (missing file,
syntax error).

Finding kinds:

| kind | meaning |
|---|---|
| `ghost-module` | the imported module cannot be imported at all — likely hallucinated |
| `ghost-api` | the module is real, but the attribute doesn't exist on it — likely hallucinated |
| `ghost-param` | the function is real, but the keyword argument isn't in its real signature |
| `deprecated` | the API advertises deprecation (`__deprecated__` per PEP 702, or a "deprecated" docstring) |
| `unverifiable` | the import itself raised an unexpected error, so existence couldn't be confirmed |

It also works as a library:

```python
from ghostapi import check_file

result = check_file("app.py")
for finding in result.findings:
    print(finding.one_line())
```

## Why not ruff / pylint?

Ruff and pylint are **static rule engines**: they match code against a fixed
list of known-bad patterns. That works for style and for APIs they already know
about, but it fundamentally can't answer the two questions that matter for
AI-generated code:

1. **"Does this API actually exist?"** — An LLM can invent a perfectly
   plausible name (`requests.post_json`, `pd.read_excel_sheets`) that no rule
   list contains. Ruff sees a valid-looking call and stays silent. `ghostapi`
   really imports the module and checks the attribute, so a hallucination is
   caught no matter how convincing it looks.
2. **"Is this real API already deprecated?"** — Deprecation is a property of the
   installed library version, not of your source text. A rule engine would need
   a constantly updated database of every library's deprecations. `ghostapi`
   reads the deprecation signals off the live objects themselves
   (`__deprecated__`, deprecation docstrings), so it tracks whatever you have
   installed.

The trade-off is deliberate: `ghostapi` only verifies names that are statically
resolvable through imports, and importing a module does run its top-level code
(it never *calls* anything). Dynamic `getattr`, monkeypatching, and
version-specific APIs can produce false negatives or positives — see
Limitations below.

## Limitations

- Only calls through imported names are checked; dynamic access
  (`getattr(mod, name)`) and monkeypatched attributes are invisible to it.
- An API that exists in your installed version but not in your deployment
  target (or vice versa) will be judged against what's installed here.
- Importing a module executes its top-level code. `ghostapi` never calls your
  functions, but a module with heavy import-time side effects will run them.
- `from x import *` and unresolvable local names are skipped, not flagged.

## Development

```bash
python3 -m unittest discover -s tests -v   # 15 tests, stdlib only
python3 -m build                            # build sdist + wheel
```

## License

MIT — see [LICENSE](LICENSE).
