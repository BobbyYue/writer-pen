"""Synthetic protocol/receipt tests, not real independent or literary-quality proof."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import review_findings as findings
import writing_execution as execution
import writing_lifecycle as lifecycle
import writing_run as wr
import test_lifecycle_guard as guards
from context_fixture import structural_reading, structural_trial


def finding(identifier='e1'):
    return dict(id=identifier, impact='The motive may remain open.',
                reason='Both concealment and hesitation are supported readings.', quote='她把信藏在身后')


class FindingValidationTests(unittest.TestCase):
    def test_absent_fields_are_legacy_and_never_added(self):
        body = dict(issues=[dict(impact='Legacy blocker')])
        before = copy.deepcopy(body)
        self.assertEqual(findings.validate(body, 'Current draft'), [])
        self.assertEqual(body, before)

    def test_optional_findings_require_all_fields_and_exact_quote(self):
        for field in ('editorial', 'suggestions'):
            valid = {field: [finding()]}
            self.assertEqual(findings.validate(valid, '门响了。她把信藏在身后。'), [])
            for name in ('id', 'impact', 'reason', 'quote'):
                for value in (None, '', ' ', 3):
                    invalid = copy.deepcopy(valid)
                    invalid[field][0][name] = value
                    with self.subTest(field=field, name=name, value=value):
                        self.assertTrue(findings.validate(invalid, '门响了。她把信藏在身后。'))
            self.assertTrue(findings.validate(valid, 'A different draft'))

    def test_bad_lists_objects_and_duplicate_ids_are_rejected(self):
        for body in (dict(editorial=None), dict(suggestions={}), dict(editorial=[None]),
                     dict(editorial=[finding(), finding()]),
                     dict(editorial=[finding()], suggestions=[finding()])):
            with self.subTest(body=body):
                self.assertTrue(findings.validate(body))

    def test_quotes_are_not_normalized_or_inferred(self):
        self.assertTrue(findings.validate(dict(editorial=[dict(finding(), quote='A B')]), 'A\nB'))
        self.assertTrue(findings.validate(dict(editorial=[dict(finding(), quote='caf\u00e9')]), 'cafe\u0301'))

    def test_legacy_verdict_equivalence_is_unchanged(self):
        base = dict(summary='A supported reading', evidence=[dict(quote='x', reason='A cue')], reading_response=structural_reading('x'))
        for verdict, issues, valid in (('pass', [], True), ('fail', [dict(impact='Legacy')], True),
                                       ('pass', [dict(impact='Legacy')], False), ('fail', [], False)):
            for extra in ({}, dict(editorial=[finding()], suggestions=[finding('s1')])):
                body = dict(base, verdict=verdict, issues=issues, **extra)
                with self.subTest(verdict=verdict, issues=issues, extra=extra):
                    if valid:
                        execution.validate_return(body, 'reader')
                    else:
                        with self.assertRaises(ValueError):
                            execution.validate_return(body, 'reader')


class EditorialProtocolTests(unittest.TestCase):
    def setUp(self):
        self.f = guards.LifecycleGuardTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.linked(complete=False)
        self.batch = self.f.begin_round()

    def register(self, **changes):
        self.f.reviewer('professional')
        self.f.reviewer('reader', **dict(dict(editorial=[finding()], suggestions=[finding('s1')]), **changes))

    def choice(self, choice='retain', **changes):
        receipt = wr.editorial_binding(wr.final_reviewers(self.f.state)['reader'])['reviewer_receipt']
        return dict(dict(draft_id='draft:v1', role='reader', finding_id='e1', reviewer_receipt=receipt,
                         choice=choice, reason='Keep the motive open at this point in the scene.',
                         trial=structural_trial(wr.current(self.f.state)['text']),
                         evidence=[dict(artifact='draft:v1', quote='她把信藏在身后')]), **changes)

    def test_new_fields_checked_by_native_and_pre_capture_validators(self):
        for field in ('editorial', 'suggestions'):
            for value in (None, [dict(finding(), quote='Only in the source')], [dict(finding(), impact='')]):
                body = self.f.reviewer_body('reader', **{field: value})
                path = self.f.put_json('malformed.json', body)
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        wr.add_reviewer_record(self.f.state, body, path)
                    with self.assertRaises(ValueError):
                        execution.validate_native_return(self.f.lifecycle, body, 'reader', self.batch['packets']['reader']['path'])
        self.assertEqual(self.f.state.get('reviewer_records', []), [])

    def test_pending_editorial_blocks_aggregate_not_raw_verdict(self):
        self.register()
        originals = [Path(r['result_path']).read_bytes() for r in wr.final_reviewers(self.f.state).values()]
        payload = wr.native_review_payload(self.f.state)
        self.assertEqual(payload['status'], 'fail')
        self.assertEqual([r['verdict'] for r in payload['reviewer_records']], ['pass', 'pass'])
        self.assertEqual(len(payload['pending_editorial']), 1)
        self.assertEqual(payload['issues'][0]['kind'], 'pending_editorial_choice')
        self.assertEqual(payload['issues'][0]['reviewer_receipt'], self.choice()['reviewer_receipt'])
        self.assertIn('pending_editorial_choice:reader/e1', self.f.check()['blockers'])
        self.assertEqual(originals, [Path(r['result_path']).read_bytes() for r in wr.final_reviewers(self.f.state).values()])

    def test_retain_records_reason_and_evidence_without_changing_reviews(self):
        self.register()
        before = copy.deepcopy(wr.final_reviewers(self.f.state))
        outcome = wr.decide_editorial(self.f.state, self.choice())
        self.assertTrue(outcome['resolved'])
        payload = wr.native_review_payload(self.f.state)
        self.assertEqual(payload['status'], 'pass')
        self.assertEqual(payload['pending_editorial'], [])
        self.assertEqual(payload['editorial_decisions'][0]['choice'], 'retain')
        self.assertEqual(wr.final_reviewers(self.f.state), before)
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')

    def test_suggestions_never_block_or_require_an_author_choice(self):
        self.register(editorial=[])
        self.assertEqual(wr.native_review_payload(self.f.state)['status'], 'pass')
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')
        with self.assertRaisesRegex(ValueError, 'not an editorial'):
            wr.decide_editorial(self.f.state, self.choice(finding_id='s1'))

    def test_author_cannot_waive_legacy_or_self_check_blockers(self):
        self.register(verdict='fail', issues=[dict(id='legacy', impact='A causal link is absent.')])
        wr.decide_editorial(self.f.state, self.choice())
        payload = wr.native_review_payload(self.f.state)
        self.assertEqual(payload['status'], 'fail')
        self.assertEqual(payload['issues'], [dict(id='legacy', impact='A causal link is absent.')])
        self.assertEqual(payload['reviewer_records'][1]['verdict'], 'fail')
        with self.assertRaisesRegex(ValueError, 'not an editorial'):
            wr.decide_editorial(self.f.state, self.choice(finding_id='legacy'))
        wr.add_review(self.f.state, self.f.review_body(issues=[self.f.issue()]))
        wr.add_review(self.f.state, self.f.review_body('comparison'))
        self.assertTrue(any(i['impact'].startswith('unresolved_issue:') for i in wr.native_review_payload(self.f.state)['issues']))

    def test_revise_defer_and_latest_choice_remain_pending(self):
        self.register()
        wr.decide_editorial(self.f.state, self.choice())
        for choice in ('revise', 'defer'):
            with self.subTest(choice=choice):
                outcome = wr.decide_editorial(self.f.state, self.choice(choice))
                self.assertFalse(outcome['resolved'])
                self.assertEqual(wr.native_review_payload(self.f.state)['status'], 'fail')
                self.assertEqual(len(wr.editorial_review_state(self.f.state)[0]), 1)

    def test_author_decision_requires_current_binding_reason_and_evidence(self):
        self.register()
        for changes in (dict(draft_id='draft:old'), dict(role='professional'), dict(finding_id='missing'),
                        dict(reviewer_receipt={'path': '/unrelated', 'sha256': 'wrong'}),
                        dict(artifact_sha256='wrong'), dict(context_id='other'), dict(packet_sha256='other'),
                        dict(choice='adopt'), dict(reason=' '), dict(evidence=[]),
                        dict(evidence=[dict(artifact='draft:v1', quote='Invented quote')])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                wr.decide_editorial(self.f.state, self.choice(**changes))
        self.assertEqual(self.f.state.get('editorial_decisions', []), [])

    def test_working_drift_or_changed_reviewer_receipt_cannot_be_approved(self):
        self.register()
        draft = wr.current(self.f.state)
        original = draft['text']
        Path(draft['origin']).write_text('Changed draft', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Working draft changed'):
            wr.decide_editorial(self.f.state, self.choice())
        Path(draft['origin']).write_text(original, encoding='utf-8')
        record = wr.final_reviewers(self.f.state)['reader']
        Path(record['result_path']).write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'reviewer result changed'):
            wr.decide_editorial(self.f.state, self.choice())

    def test_new_draft_invalidates_approval_even_with_identical_bytes(self):
        self.register()
        old_choice = self.choice()
        wr.decide_editorial(self.f.state, old_choice)
        self.f.finish_round()
        path = self.f.put('v2.md', wr.current(self.f.state)['text'])
        self.f.unit(path, suffix='2')
        wr.add_draft(self.f.state, 'v2', path, lifecycle_run=self.f.lifecycle, checkpoint='scene-1')
        self.f.reviewed()
        self.f.begin_round('2')
        for role in ('professional', 'reader'):
            self.f.reviewer(role, filename=role + '-2.json', context_id=role + '-2', editorial=[finding()])
        self.assertEqual(len(wr.editorial_review_state(self.f.state)[0]), 2)
        with self.assertRaisesRegex(ValueError, 'current draft'):
            wr.decide_editorial(self.f.state, old_choice)

    def test_new_receipt_and_role_do_not_inherit_an_approval(self):
        self.register()
        old_choice = self.choice()
        wr.decide_editorial(self.f.state, old_choice)
        self.f.finish_round()
        lifecycle.start_review(self.f.lifecycle, wr.current(self.f.state)['origin'])
        for role in ('professional', 'reader'):
            self.f.reviewer(role, filename=role + '-2.json', context_id=role + '-2', editorial=[finding()])
        pending, decisions = wr.editorial_review_state(self.f.state)
        self.assertEqual({p['role'] for p in pending}, {'reader', 'professional'})
        self.assertEqual(decisions, [])
        with self.assertRaisesRegex(ValueError, 'receipt differs'):
            wr.decide_editorial(self.f.state, old_choice)

    def test_aggregate_cannot_omit_pending_choices_or_author_evidence(self):
        self.register()
        pending = wr.native_review_payload(self.f.state)
        for field, value in (('issues', []), ('pending_editorial', []), ('status', 'pass')):
            altered = dict(pending, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                wr.bind_review_result(self.f.state, self.f.put_json('altered.json', altered))
        wr.decide_editorial(self.f.state, self.choice())
        retained = wr.native_review_payload(self.f.state)
        del retained['editorial_decisions']
        with self.assertRaisesRegex(ValueError, 'editorial_decisions'):
            wr.bind_review_result(self.f.state, self.f.put_json('missing-choice.json', retained))

    def test_new_choice_invalidates_previously_bound_aggregate(self):
        self.register()
        wr.decide_editorial(self.f.state, self.choice())
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')
        wr.decide_editorial(self.f.state, self.choice('defer'))
        result = self.f.check()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('native_review_result_predates_latest_review', result['blockers'])
        with self.assertRaises(ValueError):
            wr.deliver(self.f.state, self.f.root / 'must-not-exist.md', lifecycle_run=self.f.lifecycle)

    def test_capture_verification_still_required_for_retained_editorial(self):
        self.register()
        wr.decide_editorial(self.f.state, self.choice())
        self.f.finish_round()
        with execution.task(self.f.lifecycle, True) as task:
            task['batches']['1']['jobs'].pop('reader')
        result = self.f.check()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(any('execution_blocked:' in r for r in result['blockers']))

    def test_three_round_editorial_only_failure_is_draft_only(self):
        for number in range(1, 4):
            if number > 1:
                self.f.begin_round(str(number))
            for role in ('professional', 'reader'):
                self.f.reviewer(role, filename=f'{role}-{number}.json', context_id=f'{role}-{number}', editorial=[finding()])
            self.f.finish_round(str(number), verdict='fail')
            self.assertEqual(self.f.check()['status'], 'blocked')
            if number < 3:
                self.assertEqual(self.f.check(draft=True)['status'], 'blocked')
        result = wr.deliver(self.f.state, self.f.root / 'draft.md', lifecycle_run=self.f.lifecycle, draft=True)
        self.assertEqual(result['status'], 'review-incomplete-draft')
        self.assertEqual(len(result['pending_editorial']), 2)
        self.assertTrue(result['remaining_issues'])
        self.assertTrue(Path(result['notice_path']).is_file())
        with self.assertRaisesRegex(ValueError, 'Three review rounds exhausted'):
            lifecycle.start_review(self.f.lifecycle, wr.current(self.f.state)['origin'])

    def test_cli_records_explicit_author_choice(self):
        self.register()
        self.f.save_native()
        with lifecycle.session(self.f.lifecycle) as state:
            self.assertEqual(len(state['rounds']), 1)
            self.assertIsNone(state['rounds'][0]['verdict'])
        with wr.session(self.f.run) as state:
            self.assertEqual(len(wr.editorial_review_state(state)[0]), 1)
        path = self.f.put_json('author-choice.json', self.choice())
        result = self.f.cli('editorial-decide', self.f.run, '--file', path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['resolved'])
        self.f.state = wr.read_json(self.f.run / 'run.json')
        self.assertEqual(wr.native_review_payload(self.f.state)['status'], 'pass')
        self.f.finish_round()
        self.assertEqual(self.f.check()['status'], 'pass')
        with lifecycle.session(self.f.lifecycle) as state:
            self.assertEqual(len(state['rounds']), 1)
            self.assertEqual(state['rounds'][0]['verdict'], 'pass')

    def test_status_and_payload_mutation_cannot_change_stored_records(self):
        self.register()
        wr.decide_editorial(self.f.state, self.choice())
        before = copy.deepcopy(self.f.state)
        _, decisions = wr.editorial_review_state(self.f.state)
        decisions[0]['choice'] = 'defer'
        payload = wr.native_review_payload(self.f.state)
        payload['reviewer_records'][1]['verdict'] = 'fail'
        payload['editorial_decisions'][0]['reason'] = 'A replacement author reason'
        self.assertEqual(self.f.state, before)

    def test_changed_stored_reviewer_body_cannot_create_a_new_verdict(self):
        self.register()
        wr.final_reviewers(self.f.state)['reader']['body']['editorial'] = []
        with self.assertRaisesRegex(ValueError, 'reviewer result changed'):
            wr.native_review_payload(self.f.state)

    def test_stored_approval_is_revalidated_before_aggregation(self):
        self.register()
        wr.decide_editorial(self.f.state, self.choice())
        self.f.state['editorial_decisions'][0]['evidence'] = []
        with self.assertRaisesRegex(ValueError, 'Evidence cannot be empty'):
            wr.native_review_payload(self.f.state)
        self.assertEqual(self.f.check()['status'], 'blocked')

    def test_review_prompt_propagates_schema_for_both_roles(self):
        for role, packet in self.batch['packets'].items():
            prompt = execution.review_prompt(packet['path'], {})
            self.assertIn(findings.GUIDANCE, prompt)
            schema = json.loads(prompt.split('Native result schema:\n', 1)[1])
            self.assertEqual(schema, findings.result_schema(role, compact=True))
            self.assertIn('editorial', schema['properties'])
            self.assertNotIn('editorial', schema['required'])

    def rewrite_packet(self, role, packet):
        """Re-seal a synthetic native packet so dispatch checks more than its hash."""
        with lifecycle.session(self.f.lifecycle, True) as state:
            old = state['rounds'][-1]['packets'][role]
            lifecycle.write_json(old['path'], packet)
            replacement = lifecycle.ref(old['path'])
            state['rounds'][-1]['packets'][role] = replacement
            state['evidence'] = [replacement if item == old else item for item in state['evidence']]
        self.batch['packets'][role] = replacement

    def dispatch_packets(self):
        self.f.save_native()
        return execution.prepare_dispatch(self.f.lifecycle,
            {role: p['path'] for role, p in self.batch['packets'].items()}, self.f.run)

    def test_role_specific_method_packets_and_legacy_reader_are_accepted(self):
        import literary_methods
        for role in ('professional', 'reader'):
            packet = execution.load(self.batch['packets'][role]['path'])
            packet['literary_methods'] = literary_methods.method_packet(role)
            self.rewrite_packet(role, packet)
        self.assertEqual(self.dispatch_packets()[0], 1)
        packet = execution.load(self.batch['packets']['reader']['path'])
        del packet['literary_methods']
        self.rewrite_packet('reader', packet)
        self.assertEqual(self.dispatch_packets()[0], 1)

    def test_reader_method_cannot_carry_author_or_professional_context(self):
        import literary_methods
        original = execution.load(self.batch['packets']['reader']['path'])
        for methods in (None, {}, literary_methods.method_packet('professional'),
                        dict(literary_methods.method_packet('reader'), guidance='Author intended answer'),
                        dict(literary_methods.method_packet('reader'), author_context='Forbidden')):
            packet = dict(original, literary_methods=methods)
            self.rewrite_packet('reader', packet)
            with self.subTest(methods=methods), self.assertRaisesRegex(ValueError, 'method packet differs'):
                self.dispatch_packets()
        packet = dict(original, literary_methods=literary_methods.method_packet('reader'), author_context='Forbidden')
        self.rewrite_packet('reader', packet)
        with self.assertRaisesRegex(ValueError, 'author context or extra material'):
            self.dispatch_packets()

    def test_professional_method_packet_must_also_match_its_role(self):
        import literary_methods
        packet = execution.load(self.batch['packets']['professional']['path'])
        packet['literary_methods'] = literary_methods.method_packet('reader')
        self.rewrite_packet('professional', packet)
        with self.assertRaisesRegex(ValueError, 'method packet differs'):
            self.dispatch_packets()

    def test_invalid_capture_is_retryable_without_caching_or_new_round(self):
        self.f.save_native()
        packets = {role: p['path'] for role, p in self.batch['packets'].items()}
        attempts = []

        def captured(prompt, directory, timeout):
            attempts.append(directory)
            directory = Path(directory)
            directory.mkdir(parents=True)
            body = self.f.reviewer_body('reader', editorial=[dict(finding(), quote='Absent')])
            if len(attempts) > 1:
                body['editorial'] = [finding()]
            answer = directory / 'answer.json'
            lifecycle.write_json(answer, body)
            events = directory / 'events.jsonl'
            events.write_text('{}\n', encoding='utf-8')
            stderr = directory / 'stderr.txt'
            stderr.write_text('Synthetic fixture only', encoding='utf-8')
            return dict(answer=execution.ref(answer), events=execution.ref(events), stderr=execution.ref(stderr),
                        context_id='synthetic-reader', returncode=0, capture='fresh-codex-process')

        _, _, native = execution.prepare_dispatch(self.f.lifecycle, packets, self.f.run)
        with patch.object(execution, '_invoke', captured):
            with self.assertRaisesRegex(ValueError, 'exact current draft quote'):
                execution._job(self.f.lifecycle, 1, 'reader', packets['reader'], {}, 20, native)
            with execution.task(self.f.lifecycle) as task:
                self.assertEqual(task['batches']['1']['jobs']['reader']['status'], 'blocked')
                self.assertNotIn('captured', task['batches']['1']['jobs']['reader'])
            path = execution._job(self.f.lifecycle, 1, 'reader', packets['reader'], {}, 20, native)
        self.assertEqual(execution.load(path)['editorial'], [finding()])
        with execution.task(self.f.lifecycle) as task:
            self.assertEqual(task['batches']['1']['jobs']['reader']['attempts'], 2)
            self.assertEqual(len(task['batches']), 1)


if __name__ == '__main__':
    unittest.main()
