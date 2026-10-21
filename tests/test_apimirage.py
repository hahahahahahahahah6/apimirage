"""Smoke tests for apimirage: hallucinated APIs, bad kwargs, deprecated APIs."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))

from apimirage import check_source
from apimirage.cli import main as cli_main


def kinds(result):
    return [f.kind for f in result.findings]


class TestGhostModule(unittest.TestCase):
    def test_hallucinated_module_import(self):
        r = check_source("import no_such_module_xyz_123\n", "t.py")
        self.assertIn("ghost-module", kinds(r))
        self.assertEqual(len(r.findings), 1)

    def test_hallucinated_module_call_skipped_after_import_report(self):
        # The import site is reported once; the call through it is not double-reported.
        r = check_source("import no_such_module_xyz_123\nno_such_module_xyz_123.foo()\n", "t.py")
        self.assertEqual(kinds(r), ["ghost-module"])


class TestGhostApi(unittest.TestCase):
    def test_hallucinated_attribute_call(self):
        r = check_source("import os\nos.totally_bogus_attr_xyz()\n", "t.py")
        self.assertIn("ghost-api", kinds(r))
        self.assertTrue(any("totally_bogus_attr_xyz" in f.name for f in r.findings))

    def test_hallucinated_from_import(self):
        r = check_source("from collections import NoSuchThingAtAll\n", "t.py")
        self.assertIn("ghost-api", kinds(r))

    def test_hallucinated_nested_attribute(self):
        r = check_source("import os.path\nos.path.join_nonexistent_xyz('a')\n", "t.py")
        self.assertIn("ghost-api", kinds(r))


class TestGhostParam(unittest.TestCase):
    def test_bogus_keyword_argument(self):
        r = check_source('import os\nos.path.join("a", bogus_kwarg_xyz=1)\n', "t.py")
        self.assertIn("ghost-param", kinds(r))
        self.assertTrue(any("bogus_kwarg_xyz" in f.name for f in r.findings))

    def test_correct_kwargs_are_clean(self):
        r = check_source('import json\njson.dumps({"a": 1}, indent=2, sort_keys=True)\n', "t.py")
        self.assertEqual(r.findings, [])


class TestDeprecated(unittest.TestCase):
    def test_deprecated_docstring(self):
        r = check_source("from fakelib import old_function\nold_function()\n", "t.py")
        self.assertIn("deprecated", kinds(r))

    def test_deprecated_dunder_flag(self):
        r = check_source("import fakelib\nfakelib.legacy_thing()\n", "t.py")
        self.assertIn("deprecated", kinds(r))

    def test_non_deprecated_sibling_is_clean(self):
        r = check_source("from fakelib import new_function\nnew_function(1, y=2)\n", "t.py")
        self.assertEqual(r.findings, [])


class TestCleanCode(unittest.TestCase):
    def test_normal_stdlib_usage(self):
        src = (
            "import json\n"
            "import os\n"
            "from collections import OrderedDict\n"
            "from os import path as osp\n"
            'json.dumps({"a": 1}, indent=2)\n'
            'os.path.join("a", "b")\n'
            'osp.join("a", "b")\n'
            "OrderedDict()\n"
        )
        r = check_source(src, "t.py")
        self.assertEqual(r.findings, [])

    def test_local_names_and_star_imports_do_not_crash(self):
        src = (
            "from os import *\n"
            "from . import sibling\n"
            "from .utils import helper\n"
            "x = make_something()\n"
            "x.frobnicate(deep=True)\n"
            "callback(lambda v: v + 1)\n"
        )
        r = check_source(src, "t.py")
        self.assertEqual(r.findings, [])


class TestCli(unittest.TestCase):
    def _write(self, directory, name, content):
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_cli_exit_codes_and_text_output(self):
        with tempfile.TemporaryDirectory() as d:
            bad = self._write(d, "bad.py", "import os\nos.nope_not_real_xyz()\n")
            good = self._write(d, "good.py", "import json\njson.dumps({})\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                code_bad = cli_main([bad])
            self.assertEqual(code_bad, 1)
            self.assertIn("ghost-api", buf.getvalue())
            buf = io.StringIO()
            with redirect_stdout(buf):
                code_good = cli_main(["-q", good])
            self.assertEqual(code_good, 0)

    def test_cli_json_output(self):
        with tempfile.TemporaryDirectory() as d:
            bad = self._write(d, "bad.py", 'import os\nos.path.join("a", nope_xyz=1)\n')
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli_main(["-q", "-f", "json", bad])
            self.assertEqual(code, 1)
            data = json.loads(buf.getvalue())
            self.assertTrue(any(item["kind"] == "ghost-param" for item in data))

    def test_cli_missing_file(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli_main(["/does/not/exist_xyz.py"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
