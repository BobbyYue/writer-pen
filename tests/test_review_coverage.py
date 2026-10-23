"""Omission and conditional-action tests, not a literary-quality score."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import literary_methods as methods
import review_findings as findings
import writing_execution as execution
import writing_lifecycle as lifecycle
import writing_run as native
from context_fixture import structural_development, structural_trial
import test_lifecycle_guard as guard


EXPECTED = {'scene_continuity', 'motivation_action', 'narrator_knowledge',
            'language_detail', 'paragraph_rhythm', 'title_opening_ending', 'revision_effects'}
TEXT = '旧票\n\n他翻开抽屉。\n\n车票还在信下面。'


class CoverageTests(unittest.TestCase):
    def body(self):
        return dict(role='professional', verdict='pass', issues=[],
                    development_response=structural_development(TEXT))

    def test_registry_methods_schema_and_template_have_identical_coverage(self):
        names = set(methods.check_names())
        self.assertEqual(names, EXPECTED)
        schema = findings.result_schema('professional')['properties']['development_response']['properties']['checks']
        self.assertEqual(set(schema['required']), names)
        self.assertEqual(set(schema['properties']), names)
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(findings.development_template()['checks']), names)
        packet = methods.method_packet('professional')
        coverage = next(s for s in packet['sources'] if s['path'] == 'references/review-coverage.md')
        self.assertEqual(coverage['anchor'], '专业审稿必答项')
        for name in names:
            self.assertIn('### ' + name, packet['guidance'])
            self.assertNotIn('### ' + name, methods.method_packet('reader')['guidance'])

    def test_registry_change_cannot_silently_leave_schema_or_validator_behind(self):
        old_body = self.body()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'references').mkdir()
            source = Path(methods.__file__).resolve().parents[1] / 'references/review-coverage.md'
            (root / 'references/review-coverage.md').write_text(source.read_text() + '\n### future_check\n\nSynthetic next-version rule.\n')
            with mock.patch.object(methods, '__file__', str(root / 'scripts/literary_methods.py')):
                self.assertIn('future_check', findings.result_schema('professional')['properties']['development_response']['properties']['checks']['required'])
                self.assertIn('future_check', findings.development_template()['checks'])
                self.assertTrue(findings.validate_development(old_body, TEXT))

    def test_dispatch_schema_shares_shapes_without_changing_required_outputs(self):
        expanded = findings.result_schema('professional')
        compact = findings.result_schema('professional', compact=True)
        checks = compact['properties']['development_response']['properties']['checks']
        expected = expanded['properties']['development_response']['properties']['checks']
        self.assertEqual(checks['required'], expected['required'])
        for name, reference in checks['properties'].items():
            resolved = compact['$defs'][reference['$ref'].rsplit('/', 1)[1]]
            self.assertEqual(resolved, expected['properties'][name])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(expanded)))

    def test_every_omitted_family_and_old_two_check_return_is_rejected(self):
        for name in EXPECTED:
            body = self.body()
            del body['development_response']['checks'][name]
            with self.subTest(name=name):
                self.assertTrue(findings.validate_development(body, TEXT))
        body = self.body()
        body['development_response']['checks'] = {k: v for k, v in body['development_response']['checks'].items()
                                                  if k in ('scene_continuity', 'motivation_action')}
        self.assertTrue(findings.validate_development(body, TEXT))

    def test_check_names_cannot_be_duplicate_empty_or_unreadable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'references').mkdir()
            path = root / 'references/review-coverage.md'
            for body in ('## 专业审稿必答项\n',
                         '## 专业审稿必答项\n### a_check\nOK\n### a_check\nOK\n',
                         '## 专业审稿必答项\n### a_check\n\n',
                         '## 专业审稿必答项\n### Human heading\nOK\n'):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(ValueError):
                    methods.check_names(skill_root=root)

    def test_need_to_compare_cannot_be_closed_with_a_purpose_or_empty_trial(self):
        for trial in (None, {}, dict(current=TEXT, alternative=TEXT), structural_trial('An old draft')):
            body = self.body()
            body['development_response']['checks']['paragraph_rhythm']['comparison'] = dict(needed=True, reason='The breaks may scatter the action.', trial=trial)
            with self.subTest(trial=trial):
                self.assertTrue(findings.validate_development(body, TEXT))

    def test_real_paragraph_only_trial_can_retain_without_forcing_rewrite(self):
        body = self.body()
        check = body['development_response']['checks']['paragraph_rhythm']
        trial = dict(structural_trial(TEXT), kind='paragraphing', alternative=TEXT.replace('。\n\n车票', '。车票'))
        check['comparison'] = dict(needed=True, reason='Compare the transition into the discovery.', trial=trial)
        original = copy.deepcopy(body)
        self.assertEqual(findings.validate_development(body, TEXT), [])
        self.assertEqual(findings.validate_development(body), [])
        self.assertEqual(body, original)

    def test_suspect_passage_can_go_to_existing_editorial_resolution(self):
        body = self.body()
        body['editorial'] = [dict(id='E1', quote=TEXT, impact='The discovery may need a different pause.', reason='Two supported choices.')]
        parent = body['development_response']
        parent.update(disposition='editorial', finding_ids=['E1'])
        check = parent['checks']['paragraph_rhythm']
        check.update(disposition='editorial', finding_ids=['E1'], comparison=dict(needed=True, reason='Author should compare both layouts.', trial=None))
        self.assertEqual(findings.validate_development(body, TEXT), [])
        check['finding_ids'] = []
        self.assertTrue(findings.validate_development(body, TEXT))

    def test_no_doubt_requires_a_reason_not_an_automatic_alternative(self):
        body = self.body()
        self.assertEqual(findings.validate_development(body, TEXT), [])
        check = body['development_response']['checks']['language_detail']
        check['comparison']['reason'] = ''
        self.assertTrue(findings.validate_development(body, TEXT))
        check['comparison'] = dict(needed=False, reason='No suspect change.', trial=structural_trial(TEXT))
        self.assertTrue(findings.validate_development(body, TEXT))

    def test_static_or_untitled_work_cannot_exempt_language_paragraph_and_entry_exit(self):
        for name in ('language_detail', 'paragraph_rhythm', 'title_opening_ending'):
            body = self.body()
            body['development_response']['checks'][name]['disposition'] = 'not-applicable'
            with self.subTest(name=name):
                self.assertTrue(findings.validate_development(body, TEXT))
        body = self.body()
        for name in ('scene_continuity', 'motivation_action', 'revision_effects'):
            body['development_response']['checks'][name].update(disposition='not-applicable', observation='Synthetic static fragment without this relation.')
        self.assertEqual(findings.validate_development(body, TEXT), [])

    def test_one_paragraph_interior_is_not_a_boundary_check(self):
        body = self.body()
        check = body['development_response']['checks']['paragraph_rhythm']
        check.update(before_quote='他翻开抽屉。', after_quote='他翻开抽屉。')
        self.assertTrue(findings.validate_development(body, TEXT))
        check['after_quote'] = '车票还在信下面。'
        self.assertEqual(findings.validate_development(body, TEXT), [])

    def test_reader_is_not_required_to_fill_author_or_professional_checks(self):
        self.assertNotIn('development_response', findings.result_schema('reader')['properties'])
        self.assertNotIn('review-coverage', json.dumps(methods.method_packet('reader'), ensure_ascii=False))

    def test_legacy_blocker_objects_remain_valid_but_unstructured_items_do_not(self):
        self.assertEqual(findings.validate(dict(issues=[dict(impact='A legacy blocker')])), [])
        for item in ('A string blocker', None, {}, {'impact': ''}, {'impact': 'A blocker', 'reason': []}):
            with self.subTest(item=item):
                self.assertTrue(findings.validate(dict(issues=[item])))

    def test_retained_paragraph_trial_cannot_ignore_the_related_boundary(self):
        body = self.body()
        check = body['development_response']['checks']['paragraph_rhythm']
        check.update(before_quote='他翻开抽屉。', after_quote='车票还在信下面。')
        check['comparison'] = dict(needed=True, reason='Compare the related discovery.',
                                  trial=structural_trial('他翻开抽屉。'))
        self.assertTrue(findings.validate_development(body, TEXT))
        check['comparison']['trial'] = structural_trial(TEXT)
        self.assertEqual(findings.validate_development(body, TEXT), [])

    def test_local_language_trial_can_use_related_quote_without_copying_whole_work(self):
        body = self.body()
        check = body['development_response']['checks']['language_detail']
        check.update(before_quote='他翻开抽屉。', after_quote='车票还在信下面。')
        check['comparison'] = dict(needed=True, reason='Compare the local action with its stated consequence.',
                                  trial=structural_trial('他翻开抽屉。'))
        self.assertEqual(findings.validate_development(body, TEXT), [])

    def test_revision_checks_need_original_and_previous_candidate_anchors(self):
        baselines = [dict(id='source:1', text='An earlier source.'), dict(id='candidate:previous', text='An earlier candidate.')]
        for b in baselines:
            b['sha256'] = hashlib.sha256(b['text'].encode()).hexdigest()
        body = self.body()
        check = body['development_response']['checks']['revision_effects']
        self.assertTrue(findings.validate_development(body, TEXT, baselines=baselines))
        check['baseline_evidence'] = [dict(id=b['id'], sha256=b['sha256'], quote=b['text'], reason='Synthetic comparison anchor.') for b in baselines]
        self.assertEqual(findings.validate_development(body, TEXT, baselines=baselines), [])
        for key, value in (('id', 'invented'), ('sha256', '0' * 64), ('quote', TEXT)):
            changed = copy.deepcopy(body)
            changed['development_response']['checks']['revision_effects']['baseline_evidence'][0][key] = value
            with self.subTest(key=key):
                self.assertTrue(findings.validate_development(changed, TEXT, baselines=baselines))
        self.assertTrue(findings.validate_development(body, TEXT, baselines=[]))
        check['disposition'] = 'not-applicable'
        self.assertTrue(findings.validate_development(body, TEXT, baselines=baselines))


class CoverageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = guard.LifecycleGuardTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.linked(complete=False)
        self.batch = self.f.begin_round()

    def test_each_omission_blocks_capture_native_and_lifecycle_aggregation(self):
        for name in EXPECTED:
            body = self.f.reviewer_body('professional')
            del body['development_response']['checks'][name]
            with self.subTest(name=name):
                for operation in (
                    lambda: execution.validate_return(body, 'professional'),
                    lambda: execution.validate_native_return(self.f.lifecycle, body, 'professional', self.batch['packets']['professional']['path']),
                    lambda: native.add_reviewer_record(self.f.state, body, self.f.put_json('missing-' + name + '.json', body)),
                    lambda: lifecycle.finish_review(self.f.lifecycle, self.f.put_json('aggregate-' + name + '.json',
                        dict(reviewer_records=[body, self.f.reviewer_body('reader')])), 'pass')):
                    with self.assertRaisesRegex(ValueError, 'checks'):
                        operation()
        self.assertEqual(self.f.state.get('reviewer_records', []), [])


if __name__ == '__main__':
    unittest.main()
