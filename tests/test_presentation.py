import json
from pathlib import Path
import unittest

import test_html_output as html_tests
import test_lifecycle_guard as guard
import writing_lifecycle as lifecycle
import validate_html_output as validator


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.page = html_tests.LiteraryHtmlTests()
        self.page.setUp()
        self.addCleanup(self.page.doCleanups)
        self.flow = self.page.bound_fixture()

    def record(self, effect="unchanged", suffix="new"):
        evidence = self.page.put("browser-" + suffix + ".json", json.dumps({"synthetic": True, "claim": "Record wiring, not real rendering"}))
        path = self.page.root / ("layout-" + suffix + ".json")
        path.write_text(json.dumps({"html": str(self.page.output), "status": "inspected",
            "reason": "Synthetic updated layout evidence", "target": "test page", "viewport": "synthetic",
            "findings": "Same manuscript in this structural fixture", "reading_effect": effect,
            "reading_observation": {"quote": "门响了。", "observation": "Synthetic observation binding only", "status": "fit"},
            "reading_reason": "Test declaration only", "evidence_files": [str(self.page.output), str(evidence)]}))
        return path

    def bound(self):
        return validator.check_review_binding(self.page.output, self.page.source, self.flow.run, self.flow.lifecycle)

    def test_layout_update_reuses_review_only_after_new_inspection(self):
        self.page.alter("font-size: 18px", "font-size: 19px")
        with self.assertRaises(ValueError):
            self.bound()
        result = lifecycle.register_presentation(self.flow.lifecycle, self.record())
        self.assertEqual(result["new_semantic_rounds"], 0)
        self.assertEqual(result["rounds"], 1)
        self.assertEqual(self.bound()["status"], "pass")

    def test_visible_text_alone_does_not_establish_reading_fit(self):
        for change in ('missing', 'old-quote', 'unresolved'):
            path = self.record(suffix='reading-' + change)
            record = json.loads(path.read_text())
            if change == 'missing':
                del record['reading_observation']
            elif change == 'old-quote':
                record['reading_observation']['quote'] = 'A passage from an old manuscript'
            else:
                record['reading_observation']['status'] = 'needs-revision'
            path.write_text(json.dumps(record))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'reading_observation'):
                lifecycle.register_presentation(self.flow.lifecycle, path)

    def test_screenshot_only_evidence_cannot_complete_literary_html(self):
        page = html_tests.LiteraryHtmlTests()
        page.setUp()
        self.addCleanup(page.doCleanups)
        incomplete = page.bound_fixture(include_html=False)
        with self.assertRaisesRegex(ValueError, 'captured presentation'):
            lifecycle.verify_delivery(incomplete.lifecycle, page.source, 'literary')

    def test_changed_prose_cannot_be_waived_as_layout(self):
        self.page.alter("她把信藏在身后", "她把信撕碎了")
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            lifecycle.register_presentation(self.flow.lifecycle, self.record())

    def test_changed_paragraphs_cannot_be_waived_as_layout(self):
        self.page.alter("门响了。她把信藏在身后。", "门响了。</p><p>她把信藏在身后。")
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            lifecycle.register_presentation(self.flow.lifecycle, self.record())

    def test_uncertain_reading_effect_blocks_reuse(self):
        result = lifecycle.register_presentation(self.flow.lifecycle, self.record("uncertain"))
        self.assertEqual(result["status"], "literary-recheck-required")
        with self.assertRaisesRegex(ValueError, "new literary candidate"):
            self.bound()

    def test_current_resource_change_blocks_until_reinspected(self):
        asset = self.page.output.parent / "local.css"
        asset.write_text("p { color: black; }")
        self.page.alter("</head>", '<link rel="stylesheet" href="local.css"></head>')
        lifecycle.register_presentation(self.flow.lifecycle, self.record())
        self.assertEqual(self.bound()["status"], "pass")
        asset.write_text("p { display: none; }")
        with self.assertRaisesRegex(ValueError, "resource changed"):
            self.bound()

    def test_snapshots_preserve_history_when_original_page_changes(self):
        with lifecycle.session(self.flow.lifecycle) as state:
            snapshot = Path(state["presentations"][-1]["snapshots"][0]["snapshot"]["path"])
            before = snapshot.read_bytes()
        self.page.alter("font-size: 18px", "font-size: 20px")
        lifecycle.register_presentation(self.flow.lifecycle, self.record())
        self.assertEqual(snapshot.read_bytes(), before)
        snapshot.write_bytes(b"changed historical inspection")
        with self.assertRaises(ValueError):
            self.bound()

    def test_active_review_cannot_be_bypassed_with_presentation(self):
        lifecycle.start_review(self.flow.lifecycle, self.page.source)
        with self.assertRaisesRegex(ValueError, "active review batch"):
            lifecycle.register_presentation(self.flow.lifecycle, self.record())

    def test_page_inspection_can_follow_content_review_without_another_round(self):
        f = guard.LifecycleGuardTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.init_lifecycle(format="html")
        f.start()
        guard.wr.prepare(f.state, None, "Synthetic character exemption", "prewrite", lifecycle_run=f.lifecycle)
        f.unit(self.page.source)
        guard.wr.add_draft(f.state, "v1", self.page.source, lifecycle_run=f.lifecycle, checkpoint="scene-1")
        f.reviewed()
        guard.wr.decide(f.state, f.choice())
        f.begin_round(layout={"status": "unmeasured", "reason": "HTML inspection follows content review"})
        for role in ("professional", "reader"):
            f.reviewer(role)
        f.finish_round()
        f.save_native()
        with self.assertRaises(ValueError):
            validator.check_review_binding(self.page.output, self.page.source, f.run, f.lifecycle)
        result = lifecycle.register_presentation(f.lifecycle, self.record())
        self.assertEqual(result["rounds"], 1)
        self.assertEqual(validator.check_review_binding(self.page.output, self.page.source, f.run, f.lifecycle)["status"], "pass")

    def test_third_round_page_update_neither_exhausts_nor_resets_literary_budget(self):
        for number in (2, 3):
            lifecycle.start_review(self.flow.lifecycle, self.page.source)
            for role in ("professional", "reader"):
                self.flow.reviewer(role, filename=role + "-" + str(number) + ".json", context_id=role + "-" + str(number))
            self.flow.finish_round(str(number))
        self.flow.save_native()
        self.page.alter("font-size: 18px", "font-size: 19px")
        result = lifecycle.register_presentation(self.flow.lifecycle, self.record())
        self.assertEqual(result["rounds"], 3)
        self.assertEqual(result["new_semantic_rounds"], 0)
        self.assertEqual(self.bound()["status"], "pass")
        with self.assertRaisesRegex(ValueError, "Three review rounds"):
            lifecycle.start_review(self.flow.lifecycle, self.page.source)


if __name__ == "__main__":
    unittest.main()
