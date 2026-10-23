import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import render_html as rh
import validate_html_output as vh
import test_lifecycle_guard as guard


class LiteraryHtmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.put('story.txt', '等门\n\n她把钥匙放在鞋柜上。\n\n门外又响了一声，她没有动。\n')
        self.output = self.root / 'page/story.html'

    def put(self, name, value):
        path = self.root / name
        path.write_text(value, encoding='utf-8')
        return path

    def build(self, **options):
        return rh.render([self.source], self.output, **options)

    def validate(self, *extra, texts=None):
        args = [sys.executable, str(SCRIPTS / 'validate_html_output.py'), str(self.output)]
        for path in texts if texts is not None else [self.source]:
            args += ['--text', str(path)]
        result = subprocess.run(args + list(extra), capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def alter(self, before, after):
        self.output.write_text(self.output.read_text().replace(before, after), encoding='utf-8')

    def test_portable_page_and_exact_prose(self):
        result = self.build()
        self.assertEqual(result['status'], 'rendered-not-reviewed')
        code, output = self.validate('--expected-language', 'zh-CN')
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)['status'], 'static-checks-passed')
        self.assertEqual(vh.check_manuscripts(self.output.read_text(), [self.source]), [])

    def test_preserves_linebreaks_spaces_and_scene_spacing(self):
        self.source.write_text('题名\n\n 第一行\n第二行。\n\n\n\n最后一段。', encoding='utf-8')
        self.build()
        self.assertEqual(self.validate()[0], 0)

    def test_html_in_source_is_escaped(self):
        self.source.write_text('她说 <门>\n\n</p><script>alert(1)</script> & "也许"。', encoding='utf-8')
        self.build()
        html = self.output.read_text()
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertEqual(self.validate()[0], 0)

    def test_literal_template_words_are_not_replaced_in_prose(self):
        self.source.write_text('纸条\n\n上面写着 {{TITLE}} 和 Document title。', encoding='utf-8')
        self.build()
        self.assertEqual(self.validate()[0], 0)

    def test_title_drift_is_blocked(self):
        self.build()
        self.alter('等门', '门已关闭')
        self.assertNotEqual(self.validate()[0], 0)

    def test_prose_drift_is_blocked(self):
        self.build()
        self.alter('她没有动', '她开了门')
        self.assertNotEqual(self.validate()[0], 0)

    def test_paragraph_merge_is_blocked_even_when_characters_match(self):
        self.build()
        self.alter('鞋柜上。</p><p>门外', '鞋柜上。门外')
        code, output = self.validate()
        self.assertNotEqual(code, 0)
        self.assertIn('paragraph boundaries differ', output)

    def test_missing_manuscript_is_not_finished_validation(self):
        self.build()
        self.assertNotEqual(self.validate(texts=[])[0], 0)

    def test_multiple_versions_are_all_present(self):
        other = self.put('other.txt', '还钥匙\n\n他把钥匙递回去。')
        rh.render([self.source, other], self.output, collection_title='两个版本')
        self.assertEqual(self.validate(texts=[self.source, other])[0], 0)
        self.assertNotEqual(self.validate(texts=[other, self.source])[0], 0)

    def test_no_silent_overwrite(self):
        self.build()
        before = self.output.read_bytes()
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(self.output.read_bytes(), before)

    def test_requires_plain_title_and_body(self):
        for content in ['', '只有题名', '# 标题\n\n正文', '第一行\n第二行\n\n正文']:
            self.source.write_text(content, encoding='utf-8')
            with self.assertRaises(ValueError):
                self.build()

    def test_bad_language_rejected(self):
        with self.assertRaises(ValueError):
            self.build(language='zh\" onclick=\"oops')

    def test_external_runtime_dependency_rejected(self):
        self.build()
        self.alter('</head>', '<script src="https://cdn.example.com/a.js"></script></head>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_protocol_relative_runtime_dependency_rejected(self):
        self.build()
        self.alter('</head>', '<script src="//cdn.example.com/a.js"></script></head>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_css_import_dependency_rejected(self):
        self.build()
        self.alter('<style>', '<style>@import "https://example.com/font.css";')
        self.assertNotEqual(self.validate()[0], 0)

    def test_missing_asset_rejected(self):
        self.build()
        self.alter('</main>', '<img src="missing.png" alt=""></main>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_asset_outside_package_rejected(self):
        self.put('outside.png', 'example')
        self.build()
        self.alter('</main>', '<img src="../outside.png" alt=""></main>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_duplicate_id_rejected(self):
        self.build()
        self.alter('</main>', '<p id="work-1">注</p></main>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_broken_anchor_rejected(self):
        self.build()
        self.alter('</main>', '<a href="#missing">注</a></main>')
        self.assertNotEqual(self.validate()[0], 0)

    def test_tiny_work_not_rejected_by_language_heuristic(self):
        self.source.write_text('门\n\n她没有动。', encoding='utf-8')
        self.build()
        self.assertEqual(self.validate('--expected-language', 'zh-CN')[0], 0)

    def test_draft_notice_is_outside_prose_and_does_not_claim_review_pass(self):
        self.build(draft_notice='草稿：人物转变仍待审读。')
        self.assertEqual(self.validate()[0], 0)
        self.assertIn('草稿：人物转变仍待审读。', self.output.read_text())

    def test_untitled_does_not_invent_a_visible_title(self):
        self.source.write_text('她把钥匙放下。\n\n门响了，她没有动。', encoding='utf-8')
        self.build(untitled=True)
        self.assertNotIn('<h1', self.output.read_text())
        self.assertEqual(self.validate('--untitled')[0], 0)

    def test_untitled_still_detects_paragraph_drift(self):
        self.source.write_text('她把钥匙放下。\n\n门响了，她没有动。', encoding='utf-8')
        self.build(untitled=True)
        self.alter('放下。</p><p>门响', '放下。门响')
        self.assertNotEqual(self.validate('--untitled')[0], 0)

    def bound_fixture(self, include_html=True, complete=True):
        fixture = guard.LifecycleGuardTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.init_lifecycle(format='html')
        fixture.start()
        guard.wr.prepare(fixture.state, None, 'Synthetic fixture only', 'prewrite', lifecycle_run=fixture.lifecycle)
        self.source.write_text('门外\n\n门响了。她把信藏在身后。', encoding='utf-8')
        fixture.unit(self.source)
        guard.wr.add_draft(fixture.state, 'v1', self.source, lifecycle_run=fixture.lifecycle, checkpoint='scene-1')
        fixture.reviewed()
        guard.wr.decide(fixture.state, fixture.choice())
        self.build()
        evidence = fixture.put_json('layout.json', {'synthetic': True, 'warning': 'Not real browser evidence'})
        files = [str(evidence)] + ([str(self.output)] if include_html else [])
        fixture.begin_round(layout=dict(status='inspected', reason='Synthetic record-wiring fixture',
                            target='HTML test fixture', viewport='synthetic only', findings='No human outcome claim',
                            reading_observation=dict(quote='门响了。', observation='Synthetic reading-observation binding only, not actual visual inspection.', status='fit'),
                            evidence_files=files))
        if complete:
            for role in ('professional', 'reader'):
                fixture.reviewer(role)
            fixture.finish_round()
        fixture.save_native()
        return fixture

    def test_completed_native_flow_and_bound_html_pass(self):
        f = self.bound_fixture()
        code, output = self.validate('--run', str(f.run), '--lifecycle-run', str(f.lifecycle))
        self.assertEqual(code, 0, output)
        self.assertEqual(json.loads(output)['status'], 'record-bound-html-checks-passed')

    def test_unbound_html_cannot_claim_completed_delivery(self):
        f = self.bound_fixture(include_html=False)
        code, output = self.validate('--run', str(f.run), '--lifecycle-run', str(f.lifecycle))
        self.assertNotEqual(code, 0)
        self.assertRegex(output, 'not bound|captured presentation')

    def test_layout_only_drift_invalidates_binding(self):
        f = self.bound_fixture()
        self.alter('font-size: 18px', 'font-size: 6px')
        self.assertEqual(self.validate()[0], 0)
        self.assertNotEqual(self.validate('--run', str(f.run), '--lifecycle-run', str(f.lifecycle))[0], 0)

    def test_incomplete_native_review_cannot_be_hidden_by_html(self):
        f = self.bound_fixture(complete=False)
        self.assertNotEqual(self.validate('--run', str(f.run), '--lifecycle-run', str(f.lifecycle))[0], 0)

    def test_mismatched_run_count_rejected(self):
        self.build()
        self.assertNotEqual(self.validate('--run', str(self.root / 'not-a-run'))[0], 0)


if __name__ == '__main__':
    unittest.main()
