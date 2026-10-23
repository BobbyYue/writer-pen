"""Synthetic integration fixtures test records, not literary improvement."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from test_writing_run import SCRIPTS, WritingFixtures, wr
import writing_lifecycle as lifecycle
from lifecycle_fixture import prepare_flow
from execution_fixture import init_fixture, seed_fixture


class LifecycleGuardTests(WritingFixtures, unittest.TestCase):
    def test_generated_reader_packet_reaches_managed_dispatch(self):
        import writing_execution as execution
        self.linked(complete=False)
        batch = self.begin_round()
        self.save_native()
        packets = {r: value['path'] for r, value in batch['packets'].items()}
        number, _, native = execution.prepare_dispatch(self.lifecycle, packets, self.run)
        self.assertEqual(number, 1)
        self.assertEqual(native['draft_id'], wr.current(self.state)['id'])

    def test_reader_packet_with_author_material_still_blocks_dispatch(self):
        import writing_execution as execution
        self.linked(complete=False)
        batch = self.begin_round()
        self.save_native()
        packets = {r: value['path'] for r, value in batch['packets'].items()}
        reader = json.loads(Path(packets['reader']).read_text())
        reader['author_expected_answer'] = 'Synthetic forbidden coaching'
        unsafe = self.put_json('unsafe-reader.json', reader)
        packets['reader'] = str(unsafe)
        with self.assertRaisesRegex(ValueError, 'author context'):
            execution.prepare_dispatch(self.lifecycle, packets, self.run)

    def put_json(self, name, value):
        return self.put(name, json.dumps(value, ensure_ascii=False))

    def init_lifecycle(self, profile='literary', **changes):
        self.lifecycle = self.root / 'lifecycle'
        plan = dict(task='Synthetic literary adapter test', genre='fiction', domain='literature',
                    purpose=self.contract['goal'], scope=self.contract['scope'], language='zh', format='markdown',
                    reader=dict(knowledge='Reads fiction', need='Experience a credible hesitation'),
                    authority=dict(status='confirmed', basis='Synthetic request', reference='fixture'),
                    material=dict(mode='fiction', gaps=[]), literary_intent='Leave the relationship open',
                    writing_basis=dict(given=[], interpretations=[], choices=['Synthetic adjustable choice']),
                    working_title=dict(text='Synthetic work', reason='Synthetic prewrite registration only'),
                    constraints=list(self.contract['constraints']), reading_path=[dict(id='scene-1', purpose='A reaction to the door')])
        sources = []
        if profile == 'functional':
            plan['material']['mode'] = 'source-grounded'
            sources = [self.put('request.txt', 'Synthetic source')]
            plan['required_answers'] = [dict(id='a1', question='What?', expected='An action', source_location='request')]
        plan.update(changes)
        lifecycle.init_run(self.lifecycle, self.put_json('plan.json', plan), profile, sources)
        init_fixture(self.lifecycle)

    def unit(self, filename, unit_id='scene-1', suffix='1'):
        body = Path(filename).read_text(encoding='utf-8')
        record = self.put_json('unit-' + suffix + '.json', dict(unit_id=unit_id, summary='Read the current scene',
                    observations=[dict(quote=body, reason='The interruption and response remain connected.')]))
        return lifecycle.record_unit(self.lifecycle, filename, record)

    def reviewer_body(self, role='reader', **changes):
        with lifecycle.session(self.lifecycle) as run:
            packet = run['rounds'][-1]['packets'][role]['sha256']
            source = '\n'.join(lifecycle.text(s['path']) for s in run['sources'])
        body = dict(draft_id=wr.current(self.state)['id'], role=role, context_id='fresh-' + role,
                    packet_sha256=packet,
                    verdict='pass', summary='The reaction leaves more than one supported reading.',
                    evidence=[dict(quote='她把信藏在身后', reason='The body presents concealment without fixing its motive.')], issues=[])
        from context_fixture import structural_context, structural_attribution, structural_reading, structural_development
        text = wr.current(self.state)['text']
        if role == 'professional':
            import review_findings
            packet_body = wr.read_json(run['rounds'][-1]['packets'][role]['path'])
            body['development_response'] = structural_development(
                text, review_findings.baselines_from_packet(packet_body))
            body['context_review'] = structural_context(wr.current(self.state)['text'], 'literary')
            body['source_attribution'] = structural_attribution(text, source, 'source', 'literary')
        else:
            body['attribution_replay'] = structural_attribution(text, profile='literary')
            body['reading_response'] = structural_reading(text)
        body.update(changes)
        return body

    def reviewer(self, role, filename=None, **changes):
        body = self.reviewer_body(role, **changes)
        path = self.put_json(filename or role + '.json', body)
        return wr.add_reviewer_record(self.state, body, path)

    def test_professional_cannot_omit_context_comparison(self):
        self.linked(complete=False)
        self.begin_round()
        body = self.reviewer_body('professional')
        del body['context_review']
        with self.assertRaisesRegex(ValueError, 'context_value missing'):
            wr.add_reviewer_record(self.state, body, self.put_json('missing-context.json', body))

    def test_professional_cannot_omit_source_attribution(self):
        self.linked(complete=False)
        self.begin_round()
        body = self.reviewer_body('professional')
        del body['source_attribution']
        with self.assertRaisesRegex(ValueError, 'source_attribution missing'):
            wr.add_reviewer_record(self.state, body, self.put_json('missing-attribution.json', body))

    def test_literary_reader_cannot_omit_replay(self):
        self.linked(complete=False)
        self.begin_round()
        body = self.reviewer_body('reader')
        del body['attribution_replay']
        with self.assertRaisesRegex(ValueError, 'source_attribution missing'):
            wr.add_reviewer_record(self.state, body, self.put_json('missing-replay.json', body))

    def register_candidate(self, suffix='1', **changes):
        path = wr.current(self.state)['origin']
        report_path = self.root / ('measure-' + suffix + '.json')
        report = lifecycle.measure(self.lifecycle, path, report_path)
        assessment = dict(text_sha256=report['text_sha256'], report_sha256=lifecycle.ref(report_path)['sha256'],
                          observations=[dict(metrics=list(report['metrics']), quote='她把信藏在身后',
                        reason='Synthetic coverage only; no claim of literary quality.')],
                          dispositions=[dict(signal_id=s['id'], decision='retain',
                        reason='The signal describes an intentional scene; no ratio is a rejection rule.')
                        for metric in report['metrics'].values() for s in metric['signals']], issues=[])
        assessment.update(changes)
        lifecycle.register_candidate(self.lifecycle, path, path, report_path,
                                     self.put_json('assessment-' + suffix + '.json', assessment))

    def linked(self, complete=True, **plan_changes):
        if complete:
            self.start()
            path = self.put('v1.md', '门响了。她把信藏在身后。')
            updates = dict(purpose=self.contract['goal'], scope=self.contract['scope'],
                           constraints=list(self.contract['constraints']))
            updates.update(plan_changes)
            flow = prepare_flow(lifecycle, self.root, path, profile='literary',
                                plan_updates=updates)
            self.lifecycle = flow['run']
            wr.prepare(self.state, None, 'Synthetic character exemption', 'prewrite', lifecycle_run=self.lifecycle)
            wr.add_draft(self.state, 'v1', path, lifecycle_run=self.lifecycle, checkpoint='unit')
            self.reviewed()
            raw = wr.read_json(flow['result'])
            for record in raw['reviewer_records']:
                body = dict(record, draft_id='draft:v1')
                wr.add_reviewer_record(self.state, body, self.put_json(record['role'] + '.json', body))
            wr.decide(self.state, self.choice())
            wr.bind_review_result(self.state, flow['result'])
            self.flow = flow
            return
        self.init_lifecycle(**plan_changes)
        self.start()
        wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        path = self.put('v1.md', '门响了。她把信藏在身后。')
        self.unit(path)
        wr.add_draft(self.state, 'v1', path, lifecycle_run=self.lifecycle, checkpoint='scene-1')
        self.reviewed()
        wr.decide(self.state, self.choice())

    def begin_round(self, suffix='1', stage='after', **candidate_changes):
        self.register_candidate(suffix, **candidate_changes)
        return lifecycle.start_review(self.lifecycle, wr.current(self.state)['origin'], stage=stage)

    def finish_round(self, suffix='1', verdict='pass', **candidate_changes):
        native = wr.write_review_result(self.state, self.root / ('result-' + suffix + '.json'))
        lifecycle.finish_review(self.lifecycle, native['result_path'], verdict)
        seed_fixture(self.lifecycle, native['result_path'])
        return native

    def check(self, **options):
        return wr.check(self.state, lifecycle_run=self.lifecycle, **options)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(SCRIPTS / 'writing_run.py'), *map(str, args)],
                              capture_output=True, text=True)

    def save_native(self):
        (self.run / 'run.json').write_text(json.dumps(self.state), encoding='utf-8')

    def test_full_delivery_uses_real_lifecycle_and_exact_bytes(self):
        self.linked()
        result = wr.deliver(self.state, self.root / 'final.md', lifecycle_run=self.lifecycle)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['lifecycle']['profile'], 'literary')
        self.assertEqual(result['lifecycle']['rounds'], 1)
        self.assertEqual((self.root / 'final.md').read_bytes(), (self.root / 'v1.md').read_bytes())
        self.assertIn(str(self.flow['result'].resolve()), result['lifecycle']['evidence_paths'])

    def test_missing_lifecycle_blocks_even_complete_self_checks(self):
        self.ready()
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')
        self.assertEqual(wr.check(self.state)['status'], 'blocked')

    def test_missing_state_file_blocks(self):
        self.linked()
        (self.lifecycle / 'lifecycle.json').unlink()
        self.assertEqual(self.check()['status'], 'blocked')

    def test_wrong_profile_cannot_prepare(self):
        self.init_lifecycle(profile='functional')
        self.start()
        with self.assertRaisesRegex(wr.Invalid, 'profile'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_native_nonfiction_or_unspecified_cannot_link_fiction(self):
        self.init_lifecycle()
        self.start()
        before = (self.lifecycle / 'lifecycle.json').read_bytes()
        for permission in ('not_allowed', 'unspecified'):
            with self.subTest(permission=permission):
                self.state['contract']['fiction'] = permission
                with self.assertRaisesRegex(wr.Invalid, 'fiction permission'):
                    wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
                self.assertEqual(self.state['preparations'], [])
                self.assertNotIn('lifecycle_run', self.state)
        self.assertEqual((self.lifecycle / 'lifecycle.json').read_bytes(), before)

    def test_nonfiction_lifecycle_accepts_native_fiction_prohibition(self):
        self.init_lifecycle(material=dict(mode='nonfiction', gaps=[]))
        self.start(fiction='not_allowed')
        result = wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        self.assertEqual(result['lifecycle_run'], str(self.lifecycle.resolve()))

    def test_source_grounded_lifecycle_does_not_require_fiction_permission(self):
        self.init_lifecycle(material=dict(mode='source-grounded', gaps=[]))
        self.start(fiction='unspecified')
        wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        self.assertEqual(len(self.state['preparations']), 1)

    def test_fiction_permission_does_not_require_inventing_material(self):
        self.init_lifecycle(material=dict(mode='nonfiction', gaps=[]))
        self.start(fiction='allowed')
        wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        self.assertEqual(len(self.state['preparations']), 1)

    def test_lifecycle_cannot_omit_native_constraints(self):
        self.init_lifecycle()
        self.start(constraints=['Keep the first person'])
        with self.assertRaisesRegex(wr.Invalid, 'constraints differ'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_lifecycle_cannot_add_different_native_constraints(self):
        self.init_lifecycle(constraints=['Invent a new ending'])
        self.start(constraints=['Keep the ending'])
        with self.assertRaisesRegex(wr.Invalid, 'constraints differ'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_constraint_order_is_not_a_different_task(self):
        self.init_lifecycle(constraints=[' Keep the ending ', 'Keep the first person'])
        self.start(constraints=['Keep the first person', 'Keep the ending'])
        wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        self.assertEqual(len(self.state['preparations']), 1)

    def test_different_goal_cannot_prepare(self):
        self.init_lifecycle(purpose='Write a different story')
        self.start()
        with self.assertRaisesRegex(wr.Invalid, 'native goal'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_missing_scope_cannot_prepare(self):
        self.init_lifecycle()
        plan = wr.read_json(self.root / 'plan.json')
        plan.pop('scope')
        other = self.root / 'no-scope'
        lifecycle.init_run(other, self.put_json('no-scope-plan.json', plan), 'literary')
        self.start()
        with self.assertRaisesRegex(wr.Invalid, 'lifecycle scope'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=other)

    def test_excerpt_scope_cannot_use_whole_work_lifecycle(self):
        self.init_lifecycle()
        self.start(scope='submitted excerpt only')
        with self.assertRaisesRegex(wr.Invalid, 'native scope'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_draft_registration_rechecks_native_fiction_permission(self):
        self.linked()
        self.state['contract']['fiction'] = 'not_allowed'
        with self.assertRaisesRegex(wr.Invalid, 'fiction permission'):
            wr.add_draft(self.state, 'v2', self.root / 'v1.md', lifecycle_run=self.lifecycle, checkpoint='unit')
        self.assertEqual(len(self.state['drafts']), 1)

    def test_final_check_and_delivery_recheck_native_contract(self):
        self.linked()
        original = json.loads(json.dumps(self.state['contract']))
        for field, value, message in (('fiction', 'not_allowed', 'fiction permission'),
                                      ('fiction', 'unspecified', 'fiction permission'),
                                      ('constraints', ['Do not invent dialogue'], 'constraints differ'),
                                      ('goal', 'Another goal', 'native goal'),
                                      ('scope', 'submitted excerpt only', 'native scope')):
            with self.subTest(field=field, value=value):
                self.state['contract'] = dict(original, **{field: value})
                result = self.check()
                self.assertEqual(result['status'], 'blocked')
                self.assertTrue(any(message in reason for reason in result['blockers']))
                with self.assertRaisesRegex(wr.Invalid, message):
                    wr.deliver(self.state, self.root / 'must-not-export.md', lifecycle_run=self.lifecycle)
                self.assertFalse((self.root / 'must-not-export.md').exists())
        self.state['contract'] = original
        self.assertEqual(self.check()['status'], 'pass')

    def test_cli_blocks_native_nonfiction_attached_to_passing_fiction_run(self):
        self.linked()
        self.state['contract']['fiction'] = 'not_allowed'
        self.save_native()
        result = self.cli('check', self.run, '--lifecycle-run', self.lifecycle)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('fiction permission', result.stdout)
        result = self.cli('deliver', self.run, '--lifecycle-run', self.lifecycle, '--to', self.root / 'invalid.md')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse((self.root / 'invalid.md').exists())

    def test_wrong_profile_cannot_pass_final_guard(self):
        self.linked()
        with lifecycle.session(self.lifecycle, True) as record:
            record['profile'] = 'functional'
        result = self.check()
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(any('profile' in reason for reason in result['blockers']))

    def test_draft_registration_rejects_missing_or_stale_unit(self):
        self.init_lifecycle()
        self.start()
        wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)
        path = self.put('v1.md', '门响了。她把信藏在身后。')
        with self.assertRaisesRegex(wr.Invalid, 'checkpoint'):
            wr.add_draft(self.state, 'v1', path, lifecycle_run=self.lifecycle, checkpoint='scene-1')
        self.unit(path)
        self.put('v1.md', '另一份正文。')
        with self.assertRaisesRegex(wr.Invalid, 'changed'):
            wr.add_draft(self.state, 'v1', path, lifecycle_run=self.lifecycle, checkpoint='scene-1')

    def test_checkpoint_id_is_required(self):
        self.linked()
        with self.assertRaises(wr.Invalid):
            wr.add_draft(self.state, 'v2', self.put('v2.md', 'Another draft'), lifecycle_run=self.lifecycle)

    def test_missing_prewrite_event_cannot_prepare(self):
        self.init_lifecycle()
        with lifecycle.session(self.lifecycle, True) as record:
            record['events'] = []
        self.start()
        with self.assertRaisesRegex(wr.Invalid, 'prewrite'):
            wr.prepare(self.state, None, 'No character center', 'prewrite', lifecycle_run=self.lifecycle)

    def test_no_candidate_or_review_cannot_pass(self):
        self.linked(complete=False)
        self.assertEqual(self.check()['status'], 'blocked')

    def test_missing_measurement_and_unhandled_candidate_rejected(self):
        self.linked(complete=False)
        path = wr.current(self.state)['origin']
        with self.assertRaises(OSError):
            lifecycle.register_candidate(self.lifecycle, path, path, self.root / 'absent.json', self.root / 'absent2.json')
        report_path = self.root / 'measure.json'
        report = lifecycle.measure(self.lifecycle, path, report_path)
        record = dict(text_sha256=report['text_sha256'], report_sha256=lifecycle.ref(report_path)['sha256'],
                      observations=[dict(metrics=list(report['metrics']), quote='她把信藏在身后', reason='Test observation')],
                      dispositions=[])
        with self.assertRaisesRegex(lifecycle.LifecycleError, 'disposition'):
            lifecycle.register_candidate(self.lifecycle, path, path, report_path, self.put_json('assessment.json', record))

    def test_new_draft_cannot_reuse_old_reviews_or_lifecycle_candidate(self):
        self.linked()
        path = self.put('v2.md', '门响了。她把信藏在身后，又把门推开。')
        self.unit(path, unit_id='unit', suffix='2')
        wr.add_draft(self.state, 'v2', path, lifecycle_run=self.lifecycle, checkpoint='unit')
        result = self.check()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('missing_fresh_reader_review_for_current_draft', result['blockers'])
        self.assertTrue(any('Delivery changed' in reason for reason in result['blockers']))

    def test_working_file_drift_blocks_even_draft_export(self):
        self.linked()
        self.put('v1.md', 'Changed after review')
        self.assertEqual(self.check()['status'], 'blocked')
        self.assertEqual(self.check(draft=True)['status'], 'blocked')

    def test_swapping_lifecycle_task_is_blocked(self):
        self.linked()
        other = self.root / 'other'
        other.mkdir()
        self.put('other/lifecycle.json', '{}')
        self.assertEqual(wr.check(self.state, lifecycle_run=other)['status'], 'blocked')

    def test_character_exemption_does_not_exempt_writing_stages(self):
        self.linked(complete=False)
        self.assertFalse(self.state['contract']['require_character'])
        self.assertEqual(self.check()['status'], 'blocked')

    def test_self_checks_are_not_fresh_reviewers(self):
        self.linked()
        self.state['reviewer_records'] = []
        result = self.check()
        self.assertEqual(result['status'], 'blocked')
        self.assertIn('missing_fresh_reader_review_for_current_draft', result['blockers'])
        self.assertIn('missing_fresh_professional_review_for_current_draft', result['blockers'])

    def test_reviewers_cannot_share_context(self):
        self.linked()
        with self.assertRaises(wr.Invalid):
            self.reviewer('reader', filename='duplicate.json',
                          context_id=wr.final_reviewers(self.state)['professional']['body']['context_id'])

    def test_reviewer_cannot_use_author_context_or_wrong_packet(self):
        self.linked()
        for changes in (dict(context_id='synthetic-author'), dict(packet_sha256='old-packet')):
            with self.subTest(changes=changes), self.assertRaises(wr.Invalid):
                self.reviewer('reader', filename='invalid-context.json', **changes)

    def test_reader_packet_has_body_but_no_author_answer(self):
        self.linked()
        with lifecycle.session(self.lifecycle) as run:
            packet = wr.read_json(run['rounds'][-1]['packets']['reader']['path'])
        self.assertEqual(packet['text'], wr.current(self.state)['text'])
        self.assertNotIn('literary_intent', packet)
        self.assertNotIn('constraints', packet)

    def test_reader_cannot_omit_or_fabricate_body_evidence(self):
        self.linked()
        for quotes in ([], [dict(quote='Only in the outline', reason='Unsupported')]):
            with self.subTest(quotes=quotes), self.assertRaises(wr.Invalid):
                self.reviewer('reader', filename='invalid-reader.json', evidence=quotes)

    def test_changed_native_reviewer_or_aggregate_blocks(self):
        self.linked()
        self.put('reader.json', '{"verdict": "pass"}')
        self.assertEqual(self.check()['status'], 'blocked')
        self.flow['result'].write_text('{"status": "pass"}', encoding='utf-8')
        self.assertEqual(self.check()['status'], 'blocked')

    def test_new_review_invalidates_old_native_result(self):
        self.linked()
        lifecycle.start_review(self.lifecycle, self.root / 'v1.md')
        self.reviewer('reader', filename='reader-revised.json', context_id='fresh-reader-revised')
        self.assertIn('native_review_result_predates_latest_review', self.check()['blockers'])

    def test_native_aggregate_must_be_the_registered_lifecycle_result(self):
        self.linked()
        wr.write_review_result(self.state, self.root / 'unregistered-result.json')
        # Same JSON and hash but a different path is still not the registered result.
        self.assertTrue(any('Native final review differs' in r for r in self.check()['blockers']))

    def test_importing_a_manual_pass_stamp_cannot_replace_reviews(self):
        self.linked()
        with self.assertRaises(wr.Invalid):
            wr.bind_review_result(self.state, self.put_json('stamp.json', dict(status='pass')))

    def test_native_self_check_issue_cannot_disappear_from_imported_result(self):
        self.linked()
        wr.add_review(self.state, self.review_body(issues=[self.issue()]))
        wr.add_review(self.state, self.review_body('comparison'))
        with self.assertRaisesRegex(wr.Invalid, 'findings'):
            wr.bind_review_result(self.state, self.flow['result'])

    def test_real_final_copy_can_be_verified_without_rebinding_candidate_path(self):
        self.linked()
        final = self.put('final.md', (self.root / 'v1.md').read_text())
        self.assertEqual(self.check(final=final)['status'], 'pass')
        self.put('final.md', 'Not the reviewed work')
        self.assertEqual(self.check(final=final)['status'], 'blocked')

    def test_three_failed_batches_only_allow_draft_with_notice(self):
        self.linked(complete=False)
        for number in range(1, 4):
            self.begin_round(str(number))
            for role in ('professional', 'reader'):
                self.reviewer(role, filename=f'{role}-{number}.json', context_id=f'{role}-{number}',
                              verdict='fail', issues=[dict(impact='The motive needs an earlier cue.')])
            wr.decide(self.state, self.choice('defer'))
            self.finish_round(str(number), verdict='fail')
            if number < 3:
                self.assertEqual(self.check(draft=True)['status'], 'blocked')
        self.assertEqual(self.check()['status'], 'blocked')
        result = wr.deliver(self.state, self.root / 'draft.md', lifecycle_run=self.lifecycle, draft=True)
        self.assertEqual(result['status'], 'review-incomplete-draft')
        notice = json.loads(Path(result['notice_path']).read_text())
        self.assertEqual(notice['lifecycle']['rounds'], 3)
        self.assertFalse(notice['lifecycle']['external_action_authorized'])
        self.assertEqual((self.root / 'draft.md').read_bytes(), (self.root / 'v1.md').read_bytes())
        self.save_native()
        response = self.cli('deliver', self.run, '--lifecycle-run', self.lifecycle, '--draft', '--to', self.root / 'cli-draft.md')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)['status'], 'review-incomplete-draft')
        self.assertTrue((self.root / 'cli-draft.md.notice.json').is_file())
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.start_review(self.lifecycle, self.root / 'v1.md')

    def review_version_history(self, verdicts):
        self.linked(complete=False)
        for number, verdict in enumerate(verdicts, 1):
            if number > 1:
                path = self.put(f'v{number}.md', f'门响了。她把信藏在身后。\n她又等了{number}次敲门声。')
                self.unit(path, suffix=str(number))
                wr.add_draft(self.state, f'v{number}', path, lifecycle_run=self.lifecycle, checkpoint='scene-1')
                self.reviewed()
            self.begin_round(str(number), stage='during' if number == 1 else 'after')
            issues = [] if verdict == 'pass' else [dict(impact='The current revision no longer supports the hesitation.')]
            for role in ('professional', 'reader'):
                self.reviewer(role, filename=f'history-{role}-{number}.json', context_id=f'history-{role}-{number}',
                              verdict=verdict, issues=issues)
            if verdict == 'pass':
                resolutions = [dict(issue=identifier, outcome='fixed',
                                    reason='Synthetic current-draft closure of the earlier fixture concern',
                                    evidence=[self.cite()])
                               for identifier, issue in wr.issue_index(self.state).items()
                               if issue.get('reviewer_binding')]
                if resolutions:
                    wr.add_review(self.state, self.review_body('comparison', resolutions=resolutions))
            wr.decide(self.state, self.choice('adopt' if verdict == 'pass' else 'defer'))
            self.finish_round(str(number), verdict=verdict)
            if number < 3:
                self.assertEqual(self.check(draft=True)['status'], 'blocked')

    def assert_regression_is_draft_only(self, verdicts):
        self.review_version_history(verdicts)
        with lifecycle.session(self.lifecycle) as record:
            self.assertEqual([batch['verdict'] for batch in record['rounds']], list(verdicts))
            self.assertNotEqual(record['rounds'][0]['artifact_sha256'], record['rounds'][-1]['artifact_sha256'])
        self.assertEqual(self.check()['status'], 'blocked')
        with self.assertRaises(wr.Invalid):
            wr.deliver(self.state, self.root / 'completed.md', lifecycle_run=self.lifecycle)
        self.assertFalse((self.root / 'completed.md').exists())
        result = wr.deliver(self.state, self.root / 'regressed-draft.md', lifecycle_run=self.lifecycle, draft=True)
        self.assertEqual(result['status'], 'review-incomplete-draft')
        self.assertEqual(result['lifecycle']['rounds'], 3)
        self.assertFalse(result['lifecycle']['external_action_authorized'])
        current_issues = [issue for issue in result['lifecycle']['issues']
                          if not issue['impact'].startswith('unresolved_issue:')]
        self.assertEqual(current_issues, [dict(impact='The current revision no longer supports the hesitation.')] * 2)
        self.assertTrue(any(issue['impact'].startswith('unresolved_issue:reviewer:')
                            for issue in result['lifecycle']['issues']))
        self.assertIn('current version', result['notice'])
        self.assertIn('not independently passed', result['notice'])
        notice = wr.read_json(result['notice_path'])
        self.assertEqual(notice['status'], 'review-incomplete-draft')
        self.assertTrue(notice['lifecycle']['user_notice_required'])
        self.assertTrue(notice['lifecycle']['user_question_required'])
        self.assertEqual((self.root / 'regressed-draft.md').read_bytes(), (self.root / 'v3.md').read_bytes())
        self.assertNotEqual((self.root / 'regressed-draft.md').read_bytes(), (self.root / 'v1.md').read_bytes())
        self.save_native()
        response = self.cli('check', self.run, '--lifecycle-run', self.lifecycle)
        self.assertEqual(response.returncode, 2, response.stderr)
        response = self.cli('deliver', self.run, '--lifecycle-run', self.lifecycle, '--draft', '--to', self.root / 'cli-regressed.md')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)['status'], 'review-incomplete-draft')
        self.assertTrue((self.root / 'cli-regressed.md.notice.json').is_file())
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.start_review(self.lifecycle, self.root / 'v3.md')

    def test_early_pass_does_not_block_current_regression_draft(self):
        self.assert_regression_is_draft_only(('pass', 'fail', 'fail'))

    def test_middle_pass_does_not_block_current_regression_draft(self):
        self.assert_regression_is_draft_only(('fail', 'pass', 'fail'))

    def test_current_pass_is_not_an_incomplete_draft(self):
        self.review_version_history(('fail', 'fail', 'pass'))
        self.assertEqual(self.check()['status'], 'pass')
        self.assertEqual(self.check(draft=True)['status'], 'blocked')
        with self.assertRaises(wr.Invalid):
            wr.deliver(self.state, self.root / 'not-a-failed-draft.md', lifecycle_run=self.lifecycle, draft=True)
        self.assertFalse((self.root / 'not-a-failed-draft.md').exists())

    def test_phase_switches_and_native_repreparation_do_not_reset_rounds(self):
        self.linked(complete=False)
        stages = ('during', 'after', 'during')
        for number, stage in enumerate(stages, 1):
            if number > 1:
                before = (self.lifecycle / 'lifecycle.json').read_bytes()
                wr.prepare(self.state, None, 'Same task, next writing phase', 'during', lifecycle_run=self.lifecycle)
                self.assertEqual((self.lifecycle / 'lifecycle.json').read_bytes(), before)
                wr.add_draft(self.state, 'v' + str(number), self.root / 'v1.md',
                             lifecycle_run=self.lifecycle, checkpoint='scene-1')
                self.reviewed()
            started = self.begin_round(str(number), stage=stage)
            self.assertEqual(started['round'], number)
            for role in ('professional', 'reader'):
                self.reviewer(role, filename=f'phase-{role}-{number}.json', context_id=f'phase-{role}-{number}',
                              verdict='fail', issues=[dict(impact='The same unresolved scene needs an earlier cue.')])
            wr.decide(self.state, self.choice('defer'))
            self.finish_round(str(number), verdict='fail')
            with lifecycle.session(self.lifecycle) as record:
                self.assertEqual([batch['round'] for batch in record['rounds']], list(range(1, number + 1)))
                self.assertEqual([batch['stage'] for batch in record['rounds']], list(stages[:number]))
        self.assertEqual(self.check(draft=True)['lifecycle']['rounds'], 3)
        before = (self.lifecycle / 'lifecycle.json').read_bytes()
        for stage in ('during', 'after'):
            with self.subTest(stage=stage), self.assertRaisesRegex(lifecycle.LifecycleError, 'exhausted'):
                lifecycle.start_review(self.lifecycle, self.root / 'v1.md', stage=stage)
        self.assertEqual((self.lifecycle / 'lifecycle.json').read_bytes(), before)
        self.state['contract']['fiction'] = 'not_allowed'
        result = self.check(draft=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertTrue(any('fiction permission' in reason for reason in result['blockers']))

    def test_cli_full_check_and_delivery_use_real_guard(self):
        self.linked()
        self.save_native()
        response = self.cli('check', self.run, '--lifecycle-run', self.lifecycle)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(json.loads(response.stdout)['status'], 'pass')
        response = self.cli('deliver', self.run, '--lifecycle-run', self.lifecycle, '--to', self.root / 'final.md')
        self.assertEqual(response.returncode, 0, response.stderr)
        self.assertEqual(self.cli('deliver', self.run, '--lifecycle-run', self.lifecycle,
                                  '--to', self.root / 'final.md').returncode, 1)

    def test_cli_prepare_draft_and_reviewer_registration(self):
        self.init_lifecycle()
        self.start()
        response = self.cli('prepare', self.run, '--lifecycle-run', self.lifecycle, '--reason', 'Character exemption')
        self.assertEqual(response.returncode, 0, response.stderr)
        path = self.put('v1.md', '门响了。她把信藏在身后。')
        self.unit(path)
        response = self.cli('draft', self.run, '--lifecycle-run', self.lifecycle, '--checkpoint', 'scene-1',
                            '--id', 'v1', '--file', path)
        self.assertEqual(response.returncode, 0, response.stderr)
        self.state = wr.read_json(self.run / 'run.json')
        self.reviewed()
        wr.decide(self.state, self.choice())
        self.begin_round()
        self.save_native()
        for role in ('professional', 'reader'):
            body = self.reviewer_body(role)
            response = self.cli('review', self.run, '--file', self.put_json(role + '.json', body))
            self.assertEqual(response.returncode, 0, response.stderr)
        result_path = self.root / 'native-result.json'
        response = self.cli('review-result', self.run, '--to', result_path)
        self.assertEqual(response.returncode, 0, response.stderr)
        lifecycle.finish_review(self.lifecycle, result_path, 'pass')
        seed_fixture(self.lifecycle, result_path)
        self.assertEqual(self.cli('check', self.run, '--lifecycle-run', self.lifecycle).returncode, 0)

    def test_complete_delivery_never_overwrites_existing_content(self):
        self.linked()
        target = self.put('final.md', 'Keep the original file')
        with self.assertRaisesRegex(wr.Invalid, 'exists'):
            wr.deliver(self.state, target, lifecycle_run=self.lifecycle)
        self.assertEqual(target.read_text(), 'Keep the original file')

    def test_cli_explicit_missing_run_does_not_export(self):
        self.linked()
        self.save_native()
        target = self.root / 'final.md'
        response = self.cli('deliver', self.run, '--lifecycle-run', self.root / 'missing', '--to', target)
        self.assertEqual(response.returncode, 1)
        self.assertFalse(target.exists())

    def test_imported_aggregate_cannot_change_version_verdict_or_issue_type(self):
        self.linked()
        for field, value in (('verdict', 'fail'), ('issues', {})):
            raw = wr.read_json(self.flow['result'])
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(wr.Invalid):
                wr.bind_review_result(self.state, self.put_json('invalid-' + field + '.json', raw))
        raw = wr.read_json(self.flow['result'])
        raw['reviewer_records'][0]['draft_id'] = 'draft:old'
        with self.assertRaisesRegex(wr.Invalid, 'older draft'):
            wr.bind_review_result(self.state, self.put_json('old-aggregate.json', raw))


if __name__ == '__main__':
    unittest.main()
