"""Synthetic process checks, not literary quality or human-response evidence."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review_findings as findings
import writing_execution as execution
import writing_lifecycle as lifecycle
import writing_run as native
from context_fixture import structural_basis, structural_reading, structural_trial, structural_development
import test_lifecycle_guard as guard
import test_review_findings as editorial


class ReadingEffectTests(unittest.TestCase):
    def test_basis_separates_given_interpretation_and_adjustable_choices(self):
        value = dict(given=['They meet after work.'], interpretations=['He may mistake politeness for affection.'],
                     choices=['Try comic narration; this is not a fixed character fact.'])
        before = copy.deepcopy(value)
        self.assertEqual(findings.validate_basis(value), [])
        self.assertEqual(value, before)
        self.assertEqual(findings.validate_basis(structural_basis()), [])

    def test_missing_or_malformed_basis_cannot_initialize_literary_plan(self):
        for value in (None, {}, dict(given=[], interpretations=[], choices=[]),
                      dict(given='fact', interpretations=[], choices=['choice']),
                      dict(given=[], interpretations=[{}], choices=['choice'])):
            with self.subTest(value=value):
                self.assertTrue(findings.validate_basis(value))
        f = guard.LifecycleGuardTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        with self.assertRaisesRegex(ValueError, 'writing_basis'):
            f.init_lifecycle(writing_basis=None)
        self.assertFalse((f.root / 'lifecycle/lifecycle.json').exists())

    def test_reader_needs_both_understanding_and_experience(self):
        for key in ('understanding', 'experience'):
            response = structural_reading('The door stayed open.')
            del response[key]
            self.assertTrue(findings.validate_reading(dict(reading_response=response)))
        self.assertTrue(findings.validate_reading({}))

    def test_indifference_is_valid_and_not_automatically_a_failure(self):
        text = 'They kept meeting. Then he left.'
        response = structural_reading(text)
        response['experience']['observation'] = 'I understood the departure but did not become interested; this distance can remain.'
        body = dict(reading_response=response, verdict='pass', summary='A distant reading is supported.',
                    evidence=[dict(quote=text, reason='The distance is visible.')], issues=[])
        self.assertEqual(findings.validate_reading(body, text), [])
        execution.validate_return(body, 'reader')

    def test_needed_editorial_work_cannot_be_only_an_unlinked_response(self):
        text = 'They kept meeting. Then he left.'
        response = structural_reading(text)
        response['experience'].update(disposition='editorial', finding_ids=['E1'])
        body = dict(reading_response=response)
        self.assertTrue(findings.validate_reading(body, text))
        body['editorial'] = [dict(id='E1', quote=text, impact='The relationship is only summarized.',
                                  reason='Developing the encounter or retaining distance needs an author choice.')]
        self.assertEqual(findings.validate_reading(body, text), [])
        body['editorial'] = []
        body['suggestions'] = [dict(id='E1')]
        self.assertTrue(findings.validate_reading(body, text))

    def test_optional_suggestion_has_its_own_binding(self):
        body = dict(reading_response=structural_reading('x'), suggestions=[dict(id='S1')])
        body['reading_response']['experience'].update(disposition='suggestion', finding_ids=['S1'])
        self.assertEqual(findings.validate_reading(body, 'x'), [])
        body['reading_response']['experience']['finding_ids'] = ['S1', 'S1']
        self.assertTrue(findings.validate_reading(body, 'x'))

    def test_wrong_quotes_and_invalid_shapes_are_rejected_without_inference(self):
        for key in ('understanding', 'experience'):
            body = dict(reading_response=structural_reading('Old text'))
            self.assertTrue(findings.validate_reading(body, 'New text'))
            body['reading_response'][key]['observation'] = ''
            self.assertTrue(findings.validate_reading(body))
        for ids in (None, {}, [{}], [''], ['E1', 'E1']):
            body = dict(reading_response=structural_reading('x'), editorial=[dict(id=[])])
            body['reading_response']['experience'].update(disposition='editorial', finding_ids=ids)
            self.assertTrue(findings.validate_reading(body, 'x'))

    def test_trial_needs_actual_alternative_costs_and_current_anchor(self):
        text = 'She waited by the door. He went upstairs.'
        trial = structural_trial(text)
        self.assertEqual(findings.validate_trial(trial, text, 'She waited'), [])
        for key in trial:
            value = dict(trial)
            del value[key]
            with self.subTest(key=key):
                self.assertTrue(findings.validate_trial(value, text))
        for alternative in (text, '  ' + text.replace(' ', '\n') + ' '):
            self.assertTrue(findings.validate_trial(dict(trial, alternative=alternative), text))
        self.assertTrue(findings.validate_trial(dict(trial, current='Old passage'), text))
        self.assertTrue(findings.validate_trial(trial, text, 'Absent finding'))

    def test_schema_requires_response_for_reader_not_professional(self):
        self.assertIn('reading_response', findings.result_schema('reader')['required'])
        self.assertNotIn('reading_response', findings.result_schema('professional')['required'])
        self.assertNotIn('reading_response', findings.RESULT_SCHEMA['required'])

    def test_intentional_paragraphing_trial_is_not_an_automatic_style_failure(self):
        text = 'He waited.\n\nShe did not come.'
        trial = dict(structural_trial(text), alternative='He waited. She did not come.', kind='paragraphing')
        self.assertEqual(findings.validate_trial(trial, text), [])
        trial['alternative'] = '  He waited.\n\n  She did not come.  '
        self.assertTrue(findings.validate_trial(trial, text))


class ReadingEffectIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = guard.LifecycleGuardTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.linked(complete=False)
        self.batch = self.f.begin_round()

    def test_missing_reading_response_rejected_at_capture_and_native_registration(self):
        body = self.f.reviewer_body('reader')
        del body['reading_response']
        for operation in (lambda: execution.validate_return(body, 'reader'),
                          lambda: execution.validate_native_return(self.f.lifecycle, body, 'reader', self.batch['packets']['reader']['path']),
                          lambda: native.add_reviewer_record(self.f.state, body, self.f.put_json('incomplete.json', body))):
            with self.assertRaisesRegex(ValueError, 'reading_response'):
                operation()
        self.assertEqual(self.f.state.get('reviewer_records', []), [])

    def test_reader_experience_quotes_must_match_current_manuscript(self):
        body = self.f.reviewer_body('reader')
        body['reading_response']['experience']['quote'] = 'A line from an older draft'
        with self.assertRaisesRegex(ValueError, 'current draft'):
            execution.validate_native_return(self.f.lifecycle, body, 'reader', self.batch['packets']['reader']['path'])

    def test_reader_packet_excludes_basis_and_other_author_information(self):
        packet = json.loads(Path(self.batch['packets']['reader']['path']).read_text())
        self.assertIn('reading_response_template', packet)
        for key in ('writing_basis', 'literary_intent', 'sources', 'constraints'):
            self.assertNotIn(key, packet)
        self.f.save_native()
        execution.prepare_dispatch(self.f.lifecycle, {r: p['path'] for r, p in self.batch['packets'].items()}, self.f.run)

    def test_lifecycle_cannot_import_a_response_omitting_experience(self):
        records = [self.f.reviewer_body(role) for role in ('professional', 'reader')]
        del records[1]['reading_response']['experience']
        path = self.f.put_json('missing-response-aggregate.json', dict(reviewer_records=records))
        with self.assertRaisesRegex(ValueError, 'reading_response'):
            lifecycle.finish_review(self.f.lifecycle, path, 'pass')

    def test_preference_waiver_without_trial_cannot_close_self_review_issue(self):
        native.add_review(self.f.state, self.f.review_body(issues=[self.f.issue('preference')]))
        number = len(self.f.state['reviews'])
        resolution = dict(issue='review:' + str(number) + '/f1', outcome='accepted_tradeoff',
                          reason='It has atmosphere', evidence=[self.f.cite()])
        with self.assertRaisesRegex(ValueError, 'trial'):
            native.add_review(self.f.state, self.f.review_body('comparison', resolutions=[resolution]))

    def test_unrelated_trial_cannot_close_a_known_preference_issue(self):
        native.add_review(self.f.state, self.f.review_body(issues=[self.f.issue('preference')]))
        number = len(self.f.state['reviews'])
        resolution = dict(issue='review:' + str(number) + '/f1', outcome='accepted_tradeoff',
                          reason='This is quieter', evidence=[self.f.cite()], trial=structural_trial('她把信藏在身后'))
        with self.assertRaisesRegex(ValueError, 'original issue passage'):
            native.add_review(self.f.state, self.f.review_body('comparison', resolutions=[resolution]))

    def test_version_comparison_requires_attention_cost_not_only_purpose(self):
        for role in ('professional', 'reader'):
            self.f.reviewer(role)
        self.f.finish_round()
        body = self.f.review_body('comparison', comparisons=[dict(kind='other', before='draft:v1',
                 gain='A purpose', loss='A cost', reason='A reason', choice='retain', evidence=[self.f.cite()])])
        # Use a real earlier draft to reach the cost check rather than an ID error.
        original = native.current(self.f.state)
        path = self.f.put('v2.md', original['text'] + '门外又响了一声。')
        self.f.unit(path, suffix='v2')
        native.add_draft(self.f.state, 'v2', path, lifecycle_run=self.f.lifecycle, checkpoint='scene-1')
        native.add_review(self.f.state, self.f.review_body())
        body['draft_id'] = 'draft:v2'
        body['observations'] = self.f.review_body()['observations']
        body['comparisons'][0]['evidence'].append(self.f.cite())
        with self.assertRaisesRegex(ValueError, 'attention_cost'):
            native.add_review(self.f.state, body)


class DevelopmentResponseTests(unittest.TestCase):
    TEXT = 'The latch clicked.\n\nShe hid the letter behind her back.'
    CHECKS = findings.literary_methods.check_names()

    def body(self, disposition='supported', **changes):
        return dict(dict(role='professional', verdict='pass', issues=[],
                         development_response=dict(structural_development(self.TEXT), disposition=disposition)), **changes)

    def test_supported_response_is_required_without_mutating_records(self):
        body = self.body()
        before = copy.deepcopy(body)
        self.assertEqual(findings.validate_development(body, self.TEXT), [])
        self.assertEqual(body, before)
        for value in (None, {}, [], 'supported'):
            with self.subTest(value=value):
                self.assertTrue(findings.validate_development(dict(body, development_response=value), self.TEXT))
        del body['development_response']
        self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_each_field_is_required_and_quote_must_be_from_current_body(self):
        body = self.body()
        for key in body['development_response']:
            value = copy.deepcopy(body)
            del value['development_response'][key]
            with self.subTest(key=key):
                self.assertTrue(findings.validate_development(value, self.TEXT))
        for key in ('observation', 'quote'):
            for value in ('', ' ', None, 7):
                body['development_response'] = dict(structural_development(self.TEXT), **{key: value})
                self.assertTrue(findings.validate_development(body, self.TEXT))
        body['development_response'] = structural_development('A sentence from the earlier draft.')
        self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_checks_require_both_fixed_keys_not_a_generic_summary(self):
        for checks in (None, [], 'supported', {},
                       {'scene_continuity': {}}, {'motivation_action': {}},
                       dict(structural_development(self.TEXT)['checks'], extra={})):
            body = self.body()
            body['development_response']['checks'] = checks
            with self.subTest(checks=checks):
                self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)), 'development_response.checks')

    def test_each_check_needs_its_own_record_and_all_fields(self):
        for name in self.CHECKS:
            for item in (None, [], 'supported', {}):
                body = self.body()
                body['development_response']['checks'][name] = item
                with self.subTest(name=name, item=item):
                    self.assertTrue(findings.validate_development(body, self.TEXT))
            for key in ('before_quote', 'after_quote', 'observation', 'disposition', 'finding_ids'):
                body = self.body()
                del body['development_response']['checks'][name][key]
                with self.subTest(name=name, missing=key):
                    self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                     'development_response.checks.' + name)

    def test_check_quotes_and_observations_are_nonempty_current_body_text(self):
        for name in self.CHECKS:
            for key in ('before_quote', 'after_quote', 'observation'):
                for value in ('', ' ', None, 7):
                    body = self.body()
                    body['development_response']['checks'][name][key] = value
                    with self.subTest(name=name, key=key, value=value):
                        self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                         'checks.' + name + '.' + key + ' must be nonempty')
            for key in ('before_quote', 'after_quote'):
                body = self.body()
                body['development_response']['checks'][name][key] = 'An earlier draft or source-only passage.'
                with self.subTest(name=name, key=key):
                    self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                     'checks.' + name + '.' + key + '.*current draft')

    def test_child_dispositions_and_ids_use_the_existing_record_rules(self):
        for name in self.CHECKS:
            for disposition in (None, '', 'unknown', 'suggestion', [], {}):
                body = self.body()
                body['development_response']['checks'][name]['disposition'] = disposition
                self.assertTrue(findings.validate_development(body, self.TEXT))
            for ids in (None, {}, [{}], [''], [' '], [7], ['B1', 'B1']):
                body = self.body()
                body['development_response']['checks'][name]['finding_ids'] = ids
                self.assertTrue(findings.validate_development(body, self.TEXT))
            for disposition in ('supported', 'not-applicable'):
                body = self.body()
                body['development_response']['checks'][name].update(disposition=disposition, finding_ids=['E1'])
                self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                 'checks.' + name + '.*cannot leave finding_ids')

    def test_child_findings_must_bind_uniquely_in_the_same_matching_list(self):
        for name in self.CHECKS:
            for disposition, field in (('blocker', 'issues'), ('editorial', 'editorial')):
                entry = dict(id='F1', impact='Synthetic unresolved relationship.',
                             reason='Synthetic record only.', quote=self.TEXT)
                body = self.body(disposition, **{field: [dict(entry, id='P1'), entry]})
                body['verdict'] = 'fail' if disposition == 'blocker' else 'pass'
                body['development_response']['finding_ids'] = ['P1']
                item = body['development_response']['checks'][name]
                item.update(disposition=disposition, finding_ids=['F1'])
                before = copy.deepcopy(body)
                self.assertEqual(findings.validate_development(body, self.TEXT), [])
                self.assertEqual(body, before)
                for entries in ([dict(entry, id='P1')], body[field] + [entry]):
                    value = copy.deepcopy(body)
                    value[field] = entries
                    with self.subTest(name=name, field=field, entries=entries):
                        self.assertRegex('; '.join(findings.validate_development(value, self.TEXT)),
                                         'checks.' + name + '.*matching ' + field)
                for other in set(('issues', 'editorial', 'suggestions')) - {field}:
                    for keep_matching in (False, True):
                        value = copy.deepcopy(body)
                        value[other] = [entry]
                        if not keep_matching:
                            value[field] = [dict(entry, id='P1')]
                        with self.subTest(name=name, other=other, keep_matching=keep_matching):
                            self.assertRegex('; '.join(findings.validate_development(value, self.TEXT)),
                                             'checks.' + name + '.*(matching|ambiguous)')
                item['finding_ids'] = []
                self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                 'checks.' + name + '.*matching ' + field)

    def test_parent_cannot_hide_child_blocker_or_editorial(self):
        for name in self.CHECKS:
            for child, parents in (('blocker', ('supported', 'not-applicable', 'editorial')),
                                   ('editorial', ('supported', 'not-applicable'))):
                for parent in parents:
                    body = self.body(parent, verdict='fail' if child == 'blocker' else 'pass',
                                     issues=[dict(id='B1')] if child == 'blocker' else [], editorial=[dict(id='E1')])
                    body['development_response']['finding_ids'] = ['E1'] if parent == 'editorial' else []
                    body['development_response']['checks'][name].update(
                        disposition=child, finding_ids=['B1' if child == 'blocker' else 'E1'])
                    with self.subTest(name=name, parent=parent, child=child):
                        self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                                         'disposition must be .*checks.' + name)

    def test_mixed_child_findings_require_fail_and_keep_both_bindings(self):
        body = self.body('blocker', verdict='fail', issues=[dict(id='B1')], editorial=[dict(id='E1')])
        response = body['development_response']
        response['finding_ids'] = ['B1']
        response['checks']['scene_continuity'].update(disposition='blocker', finding_ids=['B1'])
        response['checks']['motivation_action'].update(disposition='editorial', finding_ids=['E1'])
        self.assertEqual(findings.validate_development(body, self.TEXT), [])
        body['verdict'] = 'pass'
        self.assertRegex('; '.join(findings.validate_development(body, self.TEXT)),
                         'checks.scene_continuity blocker requires verdict fail')

    def test_nonchronological_transitions_and_unknown_motives_do_not_require_new_premises(self):
        text = 'Her hand was empty.\n\nBefore that, she had slipped the letter under the door.\n\nI never learned why.'
        body = self.body()
        body['development_response'] = structural_development(text)
        body['development_response']['checks']['scene_continuity'].update(
            before_quote='Her hand was empty.', after_quote='Before that, she had slipped the letter under the door.',
            observation='The second paragraph looks back to the letter leaving her hand; the reverse order remains legible without a time or place label in every paragraph.')
        body['development_response']['checks']['motivation_action'].update(
            before_quote='she had slipped the letter under the door.', after_quote='I never learned why.',
            observation='The narrator reports the action but explicitly cannot know her motive; this limit is supported rather than filled with an invented explanation.')
        self.assertEqual(findings.validate_development(body, text), [])

    def test_wrong_role_cannot_supply_or_substitute_development_response(self):
        body = self.body(role='reader')
        self.assertTrue(findings.validate_development(body, self.TEXT))
        self.assertTrue(findings.validate_development(body, self.TEXT, 'reader'))
        self.assertEqual(findings.validate_development(dict(role='reader'), self.TEXT, 'reader'), [])

    def test_malformed_disposition_and_finding_ids_are_rejected(self):
        for disposition in (None, '', 'suggestion', [], {}):
            self.assertTrue(findings.validate_development(self.body(disposition), self.TEXT))
        for ids in (None, {}, [{}], [''], [' '], [7], ['B1', 'B1']):
            body = self.body('blocker', verdict='fail', issues=[dict(id='B1')])
            body['development_response']['finding_ids'] = ids
            with self.subTest(ids=ids):
                self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_supported_and_not_applicable_cannot_leave_finding_ids(self):
        for disposition in ('supported', 'not-applicable'):
            body = self.body(disposition)
            body['development_response']['finding_ids'] = ['E1']
            self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_blocker_needs_unique_stable_issue_ids_and_fail(self):
        issue = dict(id='B1', impact='The concealment has no stated trigger.', reason='Synthetic blocker, not a literary judgment.')
        body = self.body('blocker', verdict='fail', issues=[issue])
        body['development_response']['finding_ids'] = ['B1']
        self.assertEqual(findings.validate_development(body, self.TEXT), [])
        self.assertTrue(findings.validate_development(dict(body, verdict='pass'), self.TEXT))
        for issues in ([], None, {}, [dict(impact='No stable id')], [dict(id=[])], [dict(id='B2')], [issue, issue]):
            with self.subTest(issues=issues):
                self.assertTrue(findings.validate_development(dict(body, issues=issues), self.TEXT))
        for field in ('editorial', 'suggestions'):
            self.assertTrue(findings.validate_development(dict(body, issues=[], **{field: [issue]}), self.TEXT))
            self.assertTrue(findings.validate_development(dict(body, **{field: [issue]}), self.TEXT))
        body['development_response']['finding_ids'] = []
        self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_editorial_must_bind_editorial_not_issues_or_suggestions(self):
        entry = dict(id='E1', impact='The motive could remain open or be developed.',
                     reason='Synthetic supported alternatives.', quote=self.TEXT)
        body = self.body('editorial', editorial=[entry])
        body['development_response']['finding_ids'] = ['E1']
        self.assertEqual(findings.validate_development(body, self.TEXT), [])
        for field in ('issues', 'suggestions'):
            self.assertTrue(findings.validate_development(dict(body, editorial=[], **{field: [entry]}), self.TEXT))
            self.assertTrue(findings.validate_development(dict(body, **{field: [entry]}), self.TEXT))
        self.assertTrue(findings.validate_development(dict(body, editorial=[entry, entry]), self.TEXT))
        body['development_response']['finding_ids'] = []
        self.assertTrue(findings.validate_development(body, self.TEXT))

    def test_static_prose_can_explain_not_applicable_without_plot_or_conflict(self):
        text = 'Rain rests on the window.\n\nThe room is still.'
        body = self.body('not-applicable')
        body['development_response'] = structural_development(text)
        body['development_response'].update(disposition='not-applicable',
            observation='This static prose describes a room, with no event progression to assess; stillness is not a missing conflict.')
        for name, reason in (
                ('scene_continuity', 'Both paragraphs describe the same still room; no change of scene needs a transition.'),
                ('motivation_action', 'There is no acting character or decision in this static description, so no motive-action link is claimed.')):
            body['development_response']['checks'][name].update(before_quote='The room is still.', after_quote='The room is still.',
                disposition='not-applicable', observation=reason)
        self.assertEqual(findings.validate_development(body, text), [])
        for name in self.CHECKS:
            value = copy.deepcopy(body)
            value['development_response']['checks'][name]['observation'] = ''
            self.assertTrue(findings.validate_development(value, text))
        body['development_response']['observation'] = ''
        self.assertTrue(findings.validate_development(body, text))

    def test_schema_and_template_are_role_specific_and_not_shared_mutations(self):
        professional, reader = findings.result_schema('professional'), findings.result_schema('reader')
        self.assertIn('development_response', professional['required'])
        self.assertNotIn('development_response', reader['required'])
        self.assertNotIn('development_response', findings.RESULT_SCHEMA['required'])
        schema = professional['properties']['development_response']
        self.assertEqual(set(schema['required']), {'observation', 'quote', 'disposition', 'finding_ids', 'checks'})
        self.assertEqual(schema['properties']['disposition']['enum'], ['supported', 'blocker', 'editorial', 'not-applicable'])
        self.assertEqual(schema['properties']['finding_ids'], dict(type='array', items=dict(type='string', minLength=1)))
        template = findings.development_template()
        check_schema = schema['properties']['checks']
        self.assertEqual(set(check_schema['required']), set(self.CHECKS))
        self.assertEqual(set(check_schema['properties']), set(self.CHECKS))
        self.assertFalse(check_schema['additionalProperties'])
        self.assertEqual(set(template), set(schema['required']))
        self.assertEqual(set(template['checks']), set(self.CHECKS))
        for name in self.CHECKS:
            item = check_schema['properties'][name]
            self.assertEqual(item['type'], 'object')
            self.assertEqual(set(item['required']), {'before_quote', 'after_quote', 'observation', 'disposition', 'finding_ids', 'comparison'} |
                             ({'baseline_evidence'} if name == 'revision_effects' else set()))
            self.assertEqual(set(item['properties']), set(item['required']))
            self.assertEqual(item['properties']['disposition'], schema['properties']['disposition'])
            self.assertEqual(item['properties']['finding_ids'], schema['properties']['finding_ids'])
            for key in ('before_quote', 'after_quote', 'observation'):
                self.assertEqual(item['properties'][key], dict(type='string', minLength=1))
            self.assertEqual(template['checks'][name], dict(before_quote='', after_quote='', observation='', disposition='', finding_ids=[],
                comparison=dict(needed=False, reason='', trial=None)) |
                ({'baseline_evidence': []} if name == 'revision_effects' else {}))
        self.assertTrue(findings.validate_development(dict(development_response=template)))
        template['finding_ids'].append('B1')
        template['checks']['scene_continuity']['finding_ids'].append('B1')
        self.assertEqual(findings.development_template()['finding_ids'], [])
        self.assertEqual(findings.development_template()['checks']['scene_continuity']['finding_ids'], [])
        self.assertEqual(template['checks']['motivation_action']['finding_ids'], [])
        check_schema['properties']['scene_continuity']['required'].append('unexpected')
        self.assertNotIn('unexpected', findings.result_schema('professional')['properties']['development_response']
                         ['properties']['checks']['properties']['scene_continuity']['required'])


class DevelopmentResponseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = guard.LifecycleGuardTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.linked(complete=False)
        self.batch = self.f.begin_round()

    def assert_development_rejected(self, body, message, capture=True, cli=False):
        packet = self.batch['packets']['professional']['path']
        path = self.f.put_json('invalid-development.json', body)
        aggregate = self.f.put_json('invalid-development-aggregate.json',
            dict(reviewer_records=[body, self.f.reviewer_body('reader')], issues=body['issues']))
        before = copy.deepcopy(self.f.state)
        lifecycle_before = (self.f.lifecycle / 'lifecycle.json').read_bytes()
        operations = [
            ('native capture', lambda: execution.validate_native_return(self.f.lifecycle, body, 'professional', packet)),
            ('registration', lambda: native.add_reviewer_record(self.f.state, body, path)),
            ('lifecycle', lambda: lifecycle.finish_review(self.f.lifecycle, aggregate, body['verdict']))]
        if capture:
            operations.append(('capture', lambda: execution.validate_return(body, 'professional')))
        for entry, operation in operations:
            with self.subTest(entry=entry), self.assertRaisesRegex(ValueError, message):
                operation()
        self.assertEqual(self.f.state, before)
        self.assertEqual((self.f.lifecycle / 'lifecycle.json').read_bytes(), lifecycle_before)
        if cli:
            self.f.save_native()
            native_before = (self.f.run / 'run.json').read_bytes()
            result = self.f.cli('review', self.f.run, '--file', path)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertRegex(result.stderr, message)
            self.assertEqual((self.f.run / 'run.json').read_bytes(), native_before)

    def test_missing_or_incomplete_checks_rejected_at_all_entries_and_real_cli(self):
        for missing in ('checks', 'scene_continuity', 'motivation_action'):
            body = self.f.reviewer_body('professional')
            if missing == 'checks':
                del body['development_response']['checks']
            else:
                del body['development_response']['checks'][missing]
            with self.subTest(missing=missing):
                self.assert_development_rejected(body, 'development_response.checks', cli=True)

    def test_each_child_quote_rejects_earlier_drafts_at_native_entries_and_cli(self):
        for name in ('scene_continuity', 'motivation_action'):
            for key in ('before_quote', 'after_quote'):
                body = self.f.reviewer_body('professional')
                body['development_response']['checks'][name][key] = 'Only an older draft contains this sentence.'
                with self.subTest(name=name, key=key):
                    self.assert_development_rejected(body, 'checks.' + name + '.' + key + '.*current draft',
                                                     capture=False, cli=True)

    def test_unlinked_child_findings_cannot_use_parent_findings_at_any_entry(self):
        for name in ('scene_continuity', 'motivation_action'):
            for disposition, field in (('blocker', 'issues'), ('editorial', 'editorial')):
                entry = dict(id='P1', impact='Synthetic unresolved relationship.',
                             reason='Synthetic binding only.', quote='她把信藏在身后')
                body = self.f.reviewer_body('professional', **{field: [entry]})
                body['verdict'] = 'fail' if disposition == 'blocker' else 'pass'
                body['development_response'].update(disposition=disposition, finding_ids=['P1'])
                body['development_response']['checks'][name].update(disposition=disposition, finding_ids=['missing-child'])
                with self.subTest(name=name, disposition=disposition):
                    self.assert_development_rejected(body, 'checks.' + name + '.*matching ' + field, cli=True)

    def test_supported_parent_cannot_hide_linked_child_findings_at_any_entry(self):
        for disposition, field in (('blocker', 'issues'), ('editorial', 'editorial')):
            entry = dict(id='F1', impact='Synthetic unresolved relationship.', reason='Synthetic binding only.', quote='她把信藏在身后')
            body = self.f.reviewer_body('professional', **{field: [entry]})
            body['verdict'] = 'fail' if disposition == 'blocker' else 'pass'
            body['development_response']['checks']['motivation_action'].update(disposition=disposition, finding_ids=['F1'])
            with self.subTest(disposition=disposition):
                self.assert_development_rejected(body, 'disposition must be .*checks.motivation_action', cli=True)

    def test_missing_response_rejected_at_capture_native_registration_and_lifecycle(self):
        body = self.f.reviewer_body('professional')
        del body['development_response']
        packet = self.batch['packets']['professional']['path']
        path = self.f.put_json('missing-development.json', body)
        records = [body, self.f.reviewer_body('reader')]
        aggregate = self.f.put_json('missing-development-aggregate.json', dict(reviewer_records=records))
        for operation in (lambda: execution.validate_return(body, 'professional'),
                          lambda: execution.validate_native_return(self.f.lifecycle, body, 'professional', packet),
                          lambda: native.add_reviewer_record(self.f.state, body, path),
                          lambda: lifecycle.finish_review(self.f.lifecycle, aggregate, 'pass')):
            with self.assertRaisesRegex(ValueError, 'development_response'):
                operation()
        self.assertEqual(self.f.state.get('reviewer_records', []), [])
        with lifecycle.session(self.f.lifecycle) as state:
            self.assertIsNone(state['rounds'][-1]['verdict'])

    def test_real_cli_registration_rejects_missing_response_without_changing_state(self):
        body = self.f.reviewer_body('professional')
        del body['development_response']
        self.f.save_native()
        before = (self.f.run / 'run.json').read_bytes()
        result = self.f.cli('review', self.f.run, '--file', self.f.put_json('missing-cli-development.json', body))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('development_response', result.stderr)
        self.assertEqual((self.f.run / 'run.json').read_bytes(), before)
        body['development_response'] = structural_development(native.current(self.f.state)['text'])
        result = self.f.cli('review', self.f.run, '--file', self.f.put_json('complete-cli-development.json', body))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(native.read_json(self.f.run / 'run.json')['reviewer_records']), 1)

    def test_stale_quote_rejected_by_capture_registration_and_lifecycle(self):
        body = self.f.reviewer_body('professional')
        body['development_response']['quote'] = 'Only the old manuscript contains this.'
        packet = self.batch['packets']['professional']['path']
        aggregate = self.f.put_json('stale-development-aggregate.json', dict(reviewer_records=[body, self.f.reviewer_body('reader')]))
        for operation in (lambda: execution.validate_native_return(self.f.lifecycle, body, 'professional', packet),
                          lambda: native.add_reviewer_record(self.f.state, body, self.f.put_json('stale-development.json', body)),
                          lambda: lifecycle.finish_review(self.f.lifecycle, aggregate, 'pass')):
            with self.assertRaisesRegex(ValueError, 'development_response.quote.*current draft'):
                operation()

    def test_reader_cannot_return_professional_response_at_any_entry(self):
        body = self.f.reviewer_body('reader', development_response=structural_development(native.current(self.f.state)['text']))
        packet = self.batch['packets']['reader']['path']
        aggregate = self.f.put_json('wrong-role-aggregate.json', dict(reviewer_records=[self.f.reviewer_body('professional'), body]))
        for operation in (lambda: execution.validate_return(body, 'reader'),
                          lambda: execution.validate_native_return(self.f.lifecycle, body, 'reader', packet),
                          lambda: native.add_reviewer_record(self.f.state, body, self.f.put_json('wrong-role.json', body)),
                          lambda: lifecycle.finish_review(self.f.lifecycle, aggregate, 'pass')):
            with self.assertRaisesRegex(ValueError, 'development_response.*professional'):
                operation()

    def test_invalid_finding_bindings_are_rejected_at_each_entry(self):
        for disposition in ('blocker', 'editorial'):
            body = self.f.reviewer_body('professional')
            body['development_response'].update(disposition=disposition, finding_ids=['missing-id'])
            if disposition == 'blocker':
                body.update(verdict='fail', issues=[dict(impact='Legacy blocker without a stable id.')])
            packet = self.batch['packets']['professional']['path']
            path = self.f.put_json(disposition + '-bad-binding.json', body)
            aggregate = self.f.put_json(disposition + '-bad-aggregate.json',
                dict(reviewer_records=[body, self.f.reviewer_body('reader')], issues=body['issues']))
            for operation in (lambda: execution.validate_return(body, 'professional'),
                              lambda: execution.validate_native_return(self.f.lifecycle, body, 'professional', packet),
                              lambda: native.add_reviewer_record(self.f.state, body, path),
                              lambda: lifecycle.finish_review(self.f.lifecycle, aggregate, body['verdict'])):
                with self.subTest(disposition=disposition), self.assertRaisesRegex(ValueError, 'development_response.*matching'):
                    operation()

    def test_not_applicable_record_can_register_and_finish_without_plot_inference(self):
        body = self.f.reviewer_body('professional')
        body['development_response'].update(disposition='not-applicable',
            observation='Synthetic brief-fragment reading: the concealment is visible, but no larger plot development is claimed.')
        body['development_response']['checks']['scene_continuity'].update(disposition='not-applicable',
            before_quote='她把信藏在身后', after_quote='她把信藏在身后',
            observation='The fragment contains only this doorway reaction, not a transition to a different scene.')
        body['development_response']['checks']['motivation_action'].update(
            before_quote='门响了', after_quote='她把信藏在身后',
            observation='The sound precedes the concealment; the fragment does not claim knowledge of her private motive.')
        execution.validate_return(body, 'professional')
        execution.validate_native_return(self.f.lifecycle, body, 'professional', self.batch['packets']['professional']['path'])
        native.add_reviewer_record(self.f.state, body, self.f.put_json('static-development.json', body))
        self.f.reviewer('reader')
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')

    def test_missing_checks_capture_is_not_cached_or_counted_as_another_round(self):
        self.f.save_native()
        execution.prepare_dispatch(self.f.lifecycle, {r: p['path'] for r, p in self.batch['packets'].items()}, self.f.run)
        body = self.f.reviewer_body('professional')
        del body['development_response']['checks']
        captured = dict(answer=execution.ref(self.f.put_json('incomplete-capture.json', body)))
        with patch.object(execution, '_invoke', return_value=captured):
            with self.assertRaisesRegex(ValueError, 'development_response.checks'):
                execution._job(self.f.lifecycle, 1, 'professional', self.batch['packets']['professional']['path'], {}, 10)
        with execution.task(self.f.lifecycle) as state:
            job = state['batches']['1']['jobs']['professional']
            self.assertEqual(job['status'], 'blocked')
            self.assertNotIn('result', job)
        with lifecycle.session(self.f.lifecycle) as state:
            self.assertEqual(len(state['rounds']), 1)
            self.assertIsNone(state['rounds'][-1]['verdict'])

    def test_professional_template_and_schema_leave_reader_packet_blind(self):
        professional = execution.load(self.batch['packets']['professional']['path'])
        reader = execution.load(self.batch['packets']['reader']['path'])
        self.assertEqual(professional['development_response_template'], findings.development_template())
        for key in ('development_response_template', 'development_response', 'writing_basis', 'sources', 'literary_intent',
                    'constraints', 'author_choices', 'context_review_template'):
            self.assertNotIn(key, reader)
        prompt = execution.review_prompt(self.batch['packets']['professional']['path'], {})
        schema = json.loads(prompt.split('Native result schema:\n', 1)[1])
        self.assertIn('development_response', schema['required'])
        development = schema['properties']['development_response']
        self.assertIn('checks', development['required'])
        self.assertEqual(set(development['properties']['checks']['required']), set(findings.literary_methods.check_names()))
        self.assertEqual(professional['development_response_template']['checks'], findings.development_template()['checks'])
        self.assertIn('stable unique IDs in issues', prompt)
        self.f.save_native()
        execution.prepare_dispatch(self.f.lifecycle, {r: p['path'] for r, p in self.batch['packets'].items()}, self.f.run)

    def test_blocker_record_is_accepted_as_a_negative_review_not_transport_failure(self):
        body = self.f.reviewer_body('professional', verdict='fail',
            issues=[dict(id='B1', impact='The reaction lacks a trigger.', reason='Synthetic review judgment only.')])
        body['development_response'].update(disposition='blocker', finding_ids=['B1'])
        body['development_response']['checks']['motivation_action'].update(disposition='blocker', finding_ids=['B1'],
            before_quote='门响了', after_quote='她把信藏在身后', observation='Synthetic blocker to test transport and binding, not a literary verdict.')
        execution.validate_return(body, 'professional')
        execution.validate_native_return(self.f.lifecycle, body, 'professional', self.batch['packets']['professional']['path'])
        native.add_reviewer_record(self.f.state, body, self.f.put_json('development-blocker.json', body))
        self.f.reviewer('reader')
        payload = native.native_review_payload(self.f.state)
        self.assertEqual(payload['status'], 'fail')
        self.assertEqual(payload['issues'][0]['id'], 'B1')
        self.f.finish_round(verdict='fail')

    def test_editorial_response_uses_existing_author_choice_without_an_extra_round(self):
        entry = dict(id='E1', impact='The concealment can stay open or be expanded.',
                     reason='Two synthetic alternatives need a choice.', quote='她把信藏在身后')
        body = self.f.reviewer_body('professional', editorial=[entry])
        body['development_response'].update(disposition='editorial', finding_ids=['E1'])
        body['development_response']['checks']['motivation_action'].update(disposition='editorial', finding_ids=['E1'],
            before_quote='门响了', after_quote='她把信藏在身后', observation='Synthetic alternatives: retain the limited motive or develop it; neither is declared a factual error.')
        execution.validate_return(body, 'professional')
        execution.validate_native_return(self.f.lifecycle, body, 'professional', self.batch['packets']['professional']['path'])
        native.add_reviewer_record(self.f.state, body, self.f.put_json('development-editorial.json', body))
        self.f.reviewer('reader')
        original = copy.deepcopy(native.final_reviewers(self.f.state))
        self.assertEqual(native.native_review_payload(self.f.state)['status'], 'fail')
        binding = native.editorial_binding(original['professional'])
        choice = dict(binding, finding_id='E1', choice='retain', reason='Retain the open motive in this synthetic scene.',
                      trial=structural_trial(native.current(self.f.state)['text']), evidence=[self.f.cite()])
        self.assertTrue(native.decide_editorial(self.f.state, choice)['resolved'])
        self.assertEqual(native.final_reviewers(self.f.state), original)
        self.assertEqual(native.native_review_payload(self.f.state)['status'], 'pass')
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')
        with lifecycle.session(self.f.lifecycle) as state:
            self.assertEqual(len(state['rounds']), 1)


class EditorialTrialIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.flow = editorial.EditorialProtocolTests()
        self.flow.setUp()
        self.addCleanup(self.flow.doCleanups)
        self.flow.register()

    def test_reason_alone_cannot_retain_editorial_and_raw_review_stays_unchanged(self):
        flow = self.flow
        originals = copy.deepcopy(native.final_reviewers(flow.f.state))
        choice = flow.choice()
        del choice['trial']
        with self.assertRaisesRegex(ValueError, 'trial'):
            native.decide_editorial(flow.f.state, choice)
        self.assertEqual(native.final_reviewers(flow.f.state), originals)
        self.assertEqual(len(native.editorial_review_state(flow.f.state)[0]), 1)

    def test_real_trial_can_retain_without_another_round_or_forced_rewrite(self):
        flow = self.flow
        result = native.decide_editorial(flow.f.state, flow.choice())
        self.assertTrue(result['resolved'])
        self.assertEqual(native.native_review_payload(flow.f.state)['status'], 'pass')
        with lifecycle.session(flow.f.lifecycle) as state:
            self.assertEqual(len(state['rounds']), 1)
        self.assertEqual(len(flow.f.state['drafts']), 1)

    def test_revise_and_defer_do_not_need_a_ceremonial_trial(self):
        flow = self.flow
        for action in ('revise', 'defer'):
            choice = flow.choice(action)
            del choice['trial']
            self.assertFalse(native.decide_editorial(flow.f.state, choice)['resolved'])

    def test_editorial_can_retain_after_an_actual_paragraphing_trial(self):
        flow = self.flow
        choice = flow.choice()
        current = choice['trial']['current']
        choice['trial'].update(kind='paragraphing', alternative=current.replace('。', '。\n\n', 1))
        self.assertTrue(native.decide_editorial(flow.f.state, choice)['resolved'])


if __name__ == '__main__':
    unittest.main()
