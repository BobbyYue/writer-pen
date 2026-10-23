import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runtime_bundle as bundle


class RuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        for folder in ("scripts", "config", "references", "tests"):
            (self.source / folder).mkdir(parents=True)
        (self.source / "SKILL.md").write_text("Synthetic skill")
        (self.source / "scripts/writer.py").write_text("print('synthetic')\n")
        (self.source / "config/package.json").write_text(json.dumps({"version": "test"}))
        (self.source / "references/method.md").write_text("Original method")
        (self.source / "tests/private-fixture.txt").write_text("Not runtime material")
        self.task = self.root / "task"
        self.task.mkdir()

    def test_snapshot_survives_source_upgrade_and_excludes_test_corpus(self):
        value = bundle.pin(self.task, self.source)
        (self.source / "scripts/writer.py").write_text("new implementation")
        (self.source / "references/method.md").write_text("new method")
        runtime = bundle.verify(value)
        self.assertEqual((runtime / "references/method.md").read_text(), "Original method")
        self.assertFalse((runtime / "tests").exists())

    def test_changed_pinned_method_rejected(self):
        value = bundle.pin(self.task, self.source)
        (Path(value["root"]) / "references/method.md").write_text("Changed")
        with self.assertRaises(ValueError):
            bundle.verify(value)

    def test_added_runtime_code_rejected(self):
        value = bundle.pin(self.task, self.source)
        (Path(value["root"]) / "scripts/unregistered.py").write_text("extra")
        with self.assertRaises(ValueError):
            bundle.verify(value)

    def test_changed_manifest_rejected(self):
        value = bundle.pin(self.task, self.source)
        Path(value["manifest"]).write_text("{}")
        with self.assertRaises(ValueError):
            bundle.verify(value)

    def test_existing_pin_never_overwritten(self):
        bundle.pin(self.task, self.source)
        with self.assertRaises(FileExistsError):
            bundle.pin(self.task, self.source)

    def test_symlink_source_rejected(self):
        (self.source / "scripts/link.py").symlink_to(self.source / "scripts/writer.py")
        with self.assertRaises(ValueError):
            bundle.pin(self.task, self.source)

    def test_legacy_inspection_does_not_mutate_or_reset_rounds(self):
        path = self.task / "lifecycle.json"
        path.write_text(json.dumps({"implementation": {"engine": "old", "config": {}}, "rounds": [{}, {}, {}]}))
        before = path.read_bytes()
        result = bundle.compatibility(self.task)
        self.assertEqual(result["status"], "original-runtime-required")
        self.assertEqual(result["recorded_rounds"], 3)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
