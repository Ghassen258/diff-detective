from pathlib import Path
import tempfile
import unittest

from diff_detective import analyze, dependencies, discover


class DiffDetectiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, path, content):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")

    def test_transitive_impact_and_path(self):
        self.put("core.py", "VALUE = 42")
        self.put("service.py", "import core")
        self.put("web.py", "from service import process")
        edges, errors = dependencies(self.root)
        self.assertFalse(errors)
        report = analyze(edges, ["core.py"])
        self.assertEqual(report["impact_count"], 2)
        self.assertEqual(next(x["via"] for x in report["impacted"] if x["file"] == "web.py"), ["core.py", "service.py", "web.py"])

    def test_relative_imports(self):
        self.put("pkg/__init__.py", "")
        self.put("pkg/helpers.py", "x = 1")
        self.put("pkg/views.py", "from . import helpers")
        edges, _ = dependencies(self.root)
        self.assertIn("pkg/helpers.py", edges["pkg/views.py"])

    def test_package_imports(self):
        self.put("pkg/__init__.py", "")
        self.put("pkg/api.py", "import pkg")
        edges, _ = dependencies(self.root)
        self.assertIn("pkg/__init__.py", edges["pkg/api.py"])

    def test_cycles_do_not_loop(self):
        self.put("a.py", "import b")
        self.put("b.py", "import a")
        edges, _ = dependencies(self.root)
        self.assertEqual(analyze(edges, ["a.py"])["impact_count"], 1)

    def test_invalid_syntax_is_reported(self):
        self.put("invalid.py", "def broken(:")
        _, warnings = dependencies(self.root)
        self.assertEqual(len(warnings), 1)

    def test_skips_virtualenv(self):
        self.put(".venv/lib/hidden.py", "import x")
        self.put("visible.py", "")
        self.assertEqual(set(discover(self.root).values()), {"visible.py"})

    def test_unknown_changed_file_is_safe(self):
        self.put("a.py", "")
        result = analyze(dependencies(self.root)[0], ["deleted.py"])
        self.assertEqual(result["changed"], ["deleted.py"])
        self.assertEqual(result["impact_count"], 0)


if __name__ == "__main__":
    unittest.main()
