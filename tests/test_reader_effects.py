"""Evidence contracts and arithmetic, not proof of literary or human outcomes."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import literary_methods
import reader_study
import review_findings
import writing_execution
import writing_lifecycle
import writing_run
from context_fixture import structural_reading, structural_development
import test_lifecycle_guard as guard


class ReaderEvidenceTests(unittest.TestCase):
    def test_reader_template_requires_classified_evidence_not_a_prescribed_answer(self):
        schema = review_findings.result_schema('reader')['properties']['reading_response']['properties']['understanding']
        self.assertIn('readings', schema['required'])
        self.assertEqual(set(schema['properties']['readings']['items']['properties']['kind']['enum']), {'explicit', 'inference', 'uncertain'})
        self.assertTrue(review_findings.validate_reading({'reading_response': review_findings.reading_template()}, 'Text'))

    def test_different_supported_or_uncertain_readings_do_not_force_failure(self):
        for kind in ('explicit', 'inference', 'uncertain'):
            response = structural_reading('She left the light on.')
            response['understanding']['readings'][0].update(kind=kind, claim='I cannot tell whom she is waiting for.')
            body = dict(reading_response=response, verdict='pass', summary='No forced thematic answer.', evidence=[dict(quote='She left the light on.', reason='A visible action.')], issues=[])
            self.assertEqual(review_findings.validate_reading(body, 'She left the light on.'), [])
            writing_execution.validate_return(body, 'reader')

    def test_missing_empty_invalid_or_stale_readings_are_rejected(self):
        for readings in (None, [], {}, [None], [{'kind': 'correct', 'claim': 'x', 'quote': 'Text'}],
                         [{'kind': 'inference', 'claim': 'x', 'quote': 'Old draft'}],
                         [{'kind': 'explicit', 'claim': '', 'quote': 'Text'}]):
            response = structural_reading('Text')
            response['understanding']['readings'] = readings
            self.assertTrue(review_findings.validate_reading({'reading_response': response}, 'Text'))

    def test_levels_are_optional_typed_and_never_summed_into_verdict(self):
        body = dict(development_response=structural_development('Text'), verdict='pass', issues=[])
        self.assertEqual(review_findings.validate_development(body, 'Text'), [])
        check = body['development_response']['checks']['motivation_action']
        for level in (0, 1, 2):
            check['support_level'] = level
            self.assertEqual(review_findings.validate_development(body, 'Text'), [])
            self.assertEqual(body['verdict'], 'pass')
        for level in (True, False, -1, 3, 1.0, '2', {}, []):
            check['support_level'] = level
            self.assertTrue(review_findings.validate_development(body, 'Text'))
        check['support_level'] = None
        self.assertTrue(review_findings.validate_development(body, 'Text'))
        check['disposition'] = 'not-applicable'
        self.assertEqual(review_findings.validate_development(body, 'Text'), [])

    def test_default_development_template_does_not_demand_ratings(self):
        self.assertTrue(all('support_level' not in x for x in review_findings.development_template()['checks'].values()))


class ReaderEvidenceIntegrationTests(unittest.TestCase):
    def test_missing_evidence_cannot_enter_capture_native_or_lifecycle(self):
        fixture = guard.LifecycleGuardTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.linked(complete=False)
        batch = fixture.begin_round()
        packet_path = batch['packets']['reader']['path']
        packet = json.loads(Path(packet_path).read_text())
        self.assertIn('readings', packet['reading_response_template']['understanding'])
        self.assertNotIn('writing_basis', packet)
        self.assertNotIn('literary_intent', packet)
        reader = fixture.reviewer_body('reader')
        del reader['reading_response']['understanding']['readings']
        aggregate = fixture.put_json('missing-evidence.json', {'reviewer_records': [fixture.reviewer_body('professional'), reader]})
        for operation in (
            lambda: writing_execution.validate_return(reader, 'reader'),
            lambda: writing_execution.validate_native_return(fixture.lifecycle, reader, 'reader', packet_path),
            lambda: writing_run.add_reviewer_record(fixture.state, reader, fixture.put_json('missing-reader.json', reader)),
            lambda: writing_lifecycle.finish_review(fixture.lifecycle, aggregate, 'pass'),
        ):
            with self.assertRaisesRegex(ValueError, 'readings'):
                operation()

    def test_current_methods_reach_roles_without_additional_check_families(self):
        root = Path(__file__).resolve().parents[1]
        author = literary_methods.method_packet('author', skill_root=root)
        professional = literary_methods.method_packet('professional', skill_root=root)
        reader = literary_methods.method_packet('reader', skill_root=root)
        self.assertEqual(author['guidance'], professional['guidance'])
        for packet, section in ((author, '共用文学准则'), (reader, '独立读者回读')):
            source = next(s for s in packet['sources'] if s['path'] == 'references/literary-review.md')
            selected = literary_methods._section((root / source['path']).read_bytes(), section)
            self.assertIn(selected.strip(), packet['guidance'])
            self.assertEqual(source['section_sha256'], hashlib.sha256(selected.encode()).hexdigest())
        self.assertNotIn('support_level', reader['guidance'])
        self.assertEqual(set(literary_methods.check_names()), {'scene_continuity', 'motivation_action', 'narrator_knowledge', 'language_detail', 'paragraph_rhythm', 'title_opening_ending', 'revision_effects'})


class ReaderStudyTests(unittest.TestCase):
    TEXT = 'She left the light on.'

    def dataset(self):
        return {'artifact_sha256': hashlib.sha256(self.TEXT.encode()).hexdigest(),
                'questions': [dict(id='fact', kind='fact', question='What did she do?', criterion='Identify the stated action.'),
                              dict(id='meaning', kind='interpretation', question='How do you read the action?', criterion='Support the reading in the text, not an author answer.')],
                'records': []}

    def record(self, identity='r1', kind='human', judgment='correct', question='fact'):
        return dict(participant_id=identity, reader_type=kind, answers=[dict(question_id=question,
                    response='An actual recorded answer.', quote=self.TEXT, judgment=judgment, rationale='Evaluator rationale, not inferred by code.')])

    def test_absent_feedback_is_unmeasured_not_zero_quality(self):
        report = reader_study.summarize(self.dataset(), self.TEXT)
        for group in report['groups'].values():
            self.assertEqual(group['received_records'], 0)
            for question in group['questions']:
                self.assertIsNone(question['rate'])
                self.assertEqual(question['status'], 'unmeasured')

    def test_humans_and_models_stay_separate_and_missing_stays_in_denominator(self):
        data = self.dataset()
        data['records'] = [self.record(), dict(participant_id='r2', reader_type='human', answers=[]),
                           self.record('r3', judgment='uncertain'), self.record('m1', kind='model')]
        report = reader_study.summarize(data, self.TEXT)
        human = report['groups']['human']['questions'][0]
        self.assertEqual(human['counts'], dict(correct=1, incorrect=0, uncertain=1, missing=1))
        self.assertEqual(human['denominator'], 3)
        self.assertEqual(human['rate'], 1 / 3)
        self.assertEqual(human['status'], 'partial')
        self.assertEqual(report['groups']['model']['questions'][0]['rate'], 1)

    def test_supported_different_readings_use_support_not_agreement(self):
        data = self.dataset()
        data['records'] = [self.record(judgment='supported', question='meaning'), self.record('r2', judgment='supported', question='meaning')]
        data['records'][0]['answers'][0]['response'] = 'Possibly waiting for someone.'
        data['records'][1]['answers'][0]['response'] = 'Possibly making the room welcoming.'
        report = reader_study.summarize(data, self.TEXT)
        self.assertEqual(report['groups']['human']['questions'][1]['numerator'], 2)
        self.assertNotIn('total_score', report)

    def test_duplicates_stale_quotes_versions_and_incompatible_judgments_fail(self):
        original = self.dataset()
        original['records'] = [self.record()]
        variants = []
        item = copy.deepcopy(original); item['records'].append(copy.deepcopy(item['records'][0])); variants.append(item)
        item = copy.deepcopy(original); item['artifact_sha256'] = '0' * 64; variants.append(item)
        item = copy.deepcopy(original); item['records'][0]['answers'][0]['quote'] = 'An older draft'; variants.append(item)
        item = copy.deepcopy(original); item['records'][0]['answers'][0]['judgment'] = 'supported'; variants.append(item)
        item = copy.deepcopy(original); item['records'][0]['answers'].append(copy.deepcopy(item['records'][0]['answers'][0])); variants.append(item)
        item = copy.deepcopy(original); item['questions'][0]['criterion'] = ''; variants.append(item)
        item = copy.deepcopy(original); item['records'][0]['reader_type'] = 'all'; variants.append(item)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValueError):
                reader_study.summarize(data, self.TEXT)

    def test_cli_runs_on_actual_files_without_changing_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manuscript, feedback = root / 'work.txt', root / 'feedback.json'
            manuscript.write_text(self.TEXT)
            feedback.write_text(json.dumps(self.dataset()))
            before = (manuscript.read_bytes(), feedback.read_bytes())
            result = subprocess.run([sys.executable, str(Path(reader_study.__file__)), str(feedback), '--text', str(manuscript)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['groups']['model']['received_records'], 0)
            self.assertEqual(before, (manuscript.read_bytes(), feedback.read_bytes()))


if __name__ == '__main__':
    unittest.main()
