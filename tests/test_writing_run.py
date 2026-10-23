import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import character_record as cr
import literary_methods
import writing_run as wr


class WritingFixtures:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        self.contract = dict(mode='create', goal='Write a credible choice', scope='whole submitted story',
                             fiction='allowed', constraints=[], require_character=False,
                             character_exemption='No character-centered analysis needed for this test')

    def put(self, name, text):
        path = self.root / name
        path.write_text(text, encoding='utf-8')
        return path

    def start(self, source=None, person=False, **changes):
        self.contract.update(changes)
        if self.contract['mode'] == 'revise':
            self.contract.setdefault('source_title', None)
        self.contract['require_character'] = person
        if person:
            self.contract.pop('character_exemption', None)
        source_path = self.put('source.md', source) if source is not None else None
        wr.init_run(self.run, self.contract, source_path)
        self.state = wr.read_json(self.run / 'run.json')
        return self.state

    def prepare(self, person=False, timing='prewrite'):
        record = None
        if person:
            note = self.put('character.md', 'She fears conflict but wants to protect a neighbor.')
            result = cr.seal(note, self.root / 'sealed', 'character-v1')
            record = result['manifest']
        return wr.prepare(self.state, record, 'Initial analysis', timing)

    def draft(self, text='门响了。她把信藏在身后。', name='v1'):
        return wr.add_draft(self.state, name, self.put(name + '.md', text))

    def cite(self, identifier=None):
        identifier = identifier or wr.current(self.state)['id']
        return dict(artifact=identifier, quote=wr.objects(self.state)[identifier]['text'][:8])

    def review_body(self, phase='clean', **updates):
        draft = wr.current(self.state)
        body = dict(draft_id=draft['id'], phase=phase,
                    coverage='excerpt' if self.contract['mode'] == 'local' else 'full',
                    summary='Synthetic supported-reading fixture, not literary-quality evidence',
                    observations=[dict(claim='Synthetic coverage wiring only; the character reacts to the interruption',
                                       covers=list(literary_methods.check_names()), evidence=[self.cite()])], issues=[])
        if phase == 'comparison':
            body['comparisons'] = []
            if draft['character_id']:
                body['character'] = dict(outcome='consistent', reason='The action is supported in context',
                                          evidence=[self.cite(), self.cite(draft['character_id'])])
            source = self.state['source']
            if source and source['text'] != draft['text']:
                body['comparisons'] = [dict(kind='opening', before='source', gain='The reaction is visible',
                                            loss='Less explanatory distance', choice='adopt', reason='Fits this scene',
                                            attention_cost='Extra scene time is part of this synthetic test',
                                            evidence=[self.cite('source'), self.cite()])]
        body.update(updates)
        return body

    def choice(self, choice='adopt'):
        return dict(draft_id=wr.current(self.state)['id'], choice=choice, reason='Textual gain fits the task',
                    evidence=[self.cite()])

    def reviewed(self):
        wr.add_review(self.state, self.review_body())
        wr.add_review(self.state, self.review_body('comparison'))

    def ready(self, **options):
        self.start(**options)
        self.prepare(person=options.get('person', False))
        self.draft()
        self.reviewed()
        wr.decide(self.state, self.choice())

    def issue(self, kind='coherence', blocking=True):
        return dict(id='f1', kind=kind, blocking=blocking, claim='An unsupported action', evidence=[self.cite()])


class WritingRunTests(WritingFixtures, unittest.TestCase):
    def test_native_records_alone_do_not_authorize_export(self):
        self.ready()
        result = wr.check_records(self.state)
        self.assertEqual(result['status'], 'record_checks_satisfied')
        self.assertEqual(result['non_whitespace_chars'], len('门响了。她把信藏在身后。'))
        with self.assertRaises(wr.Invalid):
            wr.deliver(self.state, self.root / 'final.md')
        self.assertFalse((self.root / 'final.md').exists())

    def test_init_refuses_existing_directory(self):
        self.start()
        with self.assertRaises(FileExistsError):
            wr.init_run(self.run, self.contract)

    def test_revision_requires_source(self):
        with self.assertRaises(wr.Invalid):
            self.start(mode='revise', opening_text='Start')

    def test_wrong_source_opening_rejected(self):
        with self.assertRaises(wr.Invalid):
            self.start(source='Original', mode='revise', opening_text='Wrong')

    def test_draft_requires_preparation(self):
        self.start()
        with self.assertRaises(wr.Invalid):
            self.draft()

    def test_character_required_cannot_skip(self):
        self.start(person=True)
        with self.assertRaises(wr.Invalid):
            self.prepare()

    def test_character_baseline_used_and_verified(self):
        self.ready(person=True)
        wr.validate_storage(self.state)
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_character_tamper_detected(self):
        self.ready(person=True)
        (self.root / 'sealed' / 'character-v1.md').write_text('Altered', encoding='utf-8')
        with self.assertRaises(ValueError):
            wr.validate_storage(self.state)

    def test_source_drift_detected(self):
        self.start(source='原文。', mode='revise', opening_text='原文。')
        self.put('source.md', '另一个版本。')
        with self.assertRaises(wr.Invalid):
            wr.validate_storage(self.state)

    def test_snapshot_tamper_detected(self):
        self.ready()
        self.state['drafts'][0]['text'] = 'Changed directly'
        with self.assertRaises(wr.Invalid):
            wr.validate_storage(self.state)

    def test_reused_draft_id_rejected(self):
        self.ready()
        with self.assertRaises(wr.Invalid):
            self.draft()

    def test_path_like_draft_id_rejected(self):
        self.start()
        self.prepare()
        with self.assertRaises(wr.Invalid):
            wr.add_draft(self.state, '../bad', self.put('candidate.md', 'Text'))

    def test_changed_workfile_invalidates_delivery(self):
        self.ready()
        self.put('v1.md', 'Changed after review')
        self.assertTrue(any('working_draft_changed' in x for x in wr.check_records(self.state)['blockers']))
        with self.assertRaises(wr.Invalid):
            wr.deliver(self.state, self.root / 'final.md')

    def test_new_version_needs_new_reviews(self):
        self.ready()
        self.draft('门响了。她迟疑了一下才把信藏好。', 'v2')
        self.assertIn('missing_clean_review_for_current_draft', wr.check_records(self.state)['blockers'])
        self.assertIn('missing_final_choice', wr.check_records(self.state)['blockers'])

    def test_title_change_in_reviewed_workfile_invalidates_record_checks(self):
        self.start()
        self.prepare()
        story = '门响了。她把信藏在身后。'
        self.draft('# 门外\n\n' + story)
        self.reviewed()
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')
        changed = self.put('v1.md', '# 来信\n\n' + story)
        self.assertEqual(changed.read_text().partition('\n\n')[2], story)
        result = wr.check_records(self.state)
        self.assertTrue(any('working_draft_changed' in item for item in result['blockers']))

    def test_new_title_same_body_requires_fresh_reviews(self):
        self.start()
        self.prepare()
        story = '门响了。她把信藏在身后。'
        self.draft('# 门外\n\n' + story)
        self.reviewed()
        wr.decide(self.state, self.choice())
        old_review = self.review_body()
        self.draft('# 来信\n\n' + story, 'v2')
        blockers = wr.check_records(self.state)['blockers']
        self.assertIn('missing_clean_review_for_current_draft', blockers)
        self.assertIn('missing_comparison_review_for_current_draft', blockers)
        self.assertIn('missing_final_choice', blockers)
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, old_review)

    def test_wrong_review_version_rejected(self):
        self.ready()
        body = self.review_body(draft_id='draft:missing')
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_fabricated_quote_rejected(self):
        self.start()
        self.prepare()
        self.draft()
        body = self.review_body()
        body['observations'][0]['evidence'][0]['quote'] = 'This quotation is not in the draft'
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_empty_evidence_rejected(self):
        self.start()
        self.prepare()
        self.draft()
        body = self.review_body()
        body['observations'][0]['evidence'] = []
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_malformed_observation_rejected(self):
        self.start()
        self.prepare()
        self.draft()
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body(observations=['pass']))

    def test_excerpt_cannot_claim_full_review_for_full_task(self):
        self.start()
        self.prepare()
        self.draft()
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body(coverage='excerpt'))

    def test_comparison_before_clean_rejected(self):
        self.start()
        self.prepare()
        self.draft()
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body('comparison'))

    def test_clean_cannot_cite_outline_as_observation(self):
        self.ready(person=True)
        body = self.review_body()
        body['observations'][0]['evidence'].append(self.cite('character:1'))
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_changed_revision_requires_source_comparison(self):
        self.start(source='原文。', mode='revise', opening_text='原文。')
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body())
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body('comparison', comparisons=[]))

    def test_changed_opening_requires_opening_comparison(self):
        self.start(source='原文。', mode='revise', opening_text='原文。')
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body())
        body = self.review_body('comparison')
        body['comparisons'][0]['kind'] = 'other'
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_unchanged_source_can_be_retained_without_inventing_change(self):
        self.start(source='原文。', mode='revise', opening_text='原文。')
        self.prepare()
        self.draft('原文。')
        self.reviewed()
        wr.decide(self.state, self.choice('retain'))
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_changed_draft_cannot_be_called_retained_source(self):
        self.ready(source='原文。', mode='revise', opening_text='原文。')
        with self.assertRaises(wr.Invalid):
            wr.decide(self.state, self.choice('retain'))

    def test_pending_comparison_blocks_adoption(self):
        self.ready(source='原文。', mode='revise', opening_text='原文。')
        body = self.review_body('comparison')
        body['comparisons'][0]['choice'] = 'defer'
        wr.add_review(self.state, body)
        with self.assertRaises(wr.Invalid):
            wr.decide(self.state, self.choice())

    def test_new_review_invalidates_decision(self):
        self.ready()
        wr.add_review(self.state, self.review_body('comparison'))
        self.assertIn('decision_predates_latest_review', wr.check_records(self.state)['blockers'])

    def test_new_clean_requires_new_comparison(self):
        self.ready()
        wr.add_review(self.state, self.review_body())
        self.assertIn('comparison_predates_latest_clean_review', wr.check_records(self.state)['blockers'])

    def test_new_preparation_requires_new_draft(self):
        self.ready()
        wr.prepare(self.state, None, 'A new plan', 'during')
        self.assertTrue(any('preparation_changed' in x for x in wr.check_records(self.state)['blockers']))

    def test_blocking_issue_does_not_disappear_in_new_draft(self):
        self.start()
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body(issues=[self.issue()]))
        self.draft('门响了。她辨出送信人的脚步才起身。', 'v2')
        self.reviewed()
        self.assertIn('unresolved_issue:review:1/f1', wr.check_records(self.state)['blockers'])

    def test_fix_needs_new_text_and_current_evidence(self):
        self.start()
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body(issues=[self.issue()]))
        resolution = dict(issue='review:1/f1', outcome='fixed', reason='Now the cue precedes the response', evidence=[self.cite()])
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        self.draft('门响了。她辨出送信人的脚步才起身。', 'v2')
        wr.add_review(self.state, self.review_body())
        resolution['evidence'] = [self.cite()]
        wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_false_positive_can_be_withdrawn(self):
        self.start()
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body(issues=[self.issue()]))
        resolution = dict(issue='review:1/f1', outcome='withdrawn', reason='The earlier cue already supports it', evidence=[self.cite()])
        wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_cannot_trade_away_constraint_or_coherence(self):
        for kind in ('constraint', 'coherence'):
            with self.subTest(kind=kind):
                self.start() if not hasattr(self, 'state') else None
                if not self.state['drafts']:
                    self.prepare()
                    self.draft()
                result = wr.add_review(self.state, self.review_body(issues=[self.issue(kind)]))
                resolution = dict(issue=result['issues'][0], outcome='accepted_tradeoff', reason='Faster', evidence=[self.cite()])
                with self.assertRaises(wr.Invalid):
                    wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))

    def test_preference_can_be_accepted_with_reason(self):
        self.start()
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body(issues=[self.issue('preference')]))
        resolution = dict(issue='review:1/f1', outcome='accepted_tradeoff', reason='Slower pacing suits this moment', evidence=[self.cite()])
        from context_fixture import structural_trial
        resolution['trial'] = structural_trial(wr.current(self.state)['text'])
        wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        wr.decide(self.state, self.choice())
        self.assertFalse(wr.check_records(self.state)['blockers'])

    def test_advisory_does_not_force_rewrite(self):
        self.start()
        self.prepare()
        self.draft()
        wr.add_review(self.state, self.review_body(issues=[self.issue('preference', False)]))
        wr.add_review(self.state, self.review_body('comparison'))
        wr.decide(self.state, self.choice())
        self.assertFalse(wr.check_records(self.state)['blockers'])
        self.assertEqual(wr.check_records(self.state)['advisory_issues'], ['review:1/f1'])

    def test_constraint_cannot_be_advisory(self):
        self.start()
        self.prepare()
        self.draft()
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, self.review_body(issues=[self.issue('constraint', False)]))

    def test_character_development_requires_new_sealed_record(self):
        self.ready(person=True)
        body = self.review_body('comparison')
        body['character']['outcome'] = 'development'
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)
        note = self.put('development.md', 'During writing: she intervenes despite fear when someone is threatened.')
        record = cr.seal(note, self.root / 'sealed', 'character-v2')['manifest']
        body['character']['development_record'] = record
        wr.add_review(self.state, body)
        self.assertEqual(len(self.state['characters']), 2)
        self.assertEqual(self.state['drafts'][0]['character_id'], 'character:1')
        cr.verify(self.root / 'sealed' / 'character-v1.record.json')

    def test_unsupported_character_blocks_delivery(self):
        self.ready(person=True)
        body = self.review_body('comparison')
        body['character']['outcome'] = 'unsupported'
        wr.add_review(self.state, body)
        self.assertIn('unsupported_character_change', wr.check_records(self.state)['blockers'])

    def test_development_cannot_reuse_unchanged_baseline(self):
        self.ready(person=True)
        body = self.review_body('comparison')
        body['character']['outcome'] = 'development'
        body['character']['development_record'] = str(self.root / 'sealed' / 'character-v1.record.json')
        with self.assertRaises(wr.Invalid):
            wr.add_review(self.state, body)

    def test_retrospective_record_is_not_reported_as_prewrite(self):
        self.start()
        self.prepare(timing='retrospective')
        self.draft()
        self.reviewed()
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['timing'], 'retrospective')

    def test_word_limit_is_explicit_not_universal(self):
        self.start(max_chars=2)
        self.prepare()
        self.draft()
        self.assertTrue(any('character_limit' in x for x in wr.check_records(self.state)['blockers']))

    def test_required_exact_text_enforced(self):
        self.start(preserve_exact=['Required phrase'])
        self.prepare()
        self.draft()
        self.assertIn('required_text_missing', wr.check_records(self.state)['blockers'])

    def test_local_edit_boundaries(self):
        self.start(source='LEFT middle RIGHT', mode='local', edit_span=[5, 11])
        self.prepare()
        self.draft('LEFT revised RIGHT')
        self.reviewed()
        wr.decide(self.state, self.choice())
        self.assertFalse(wr.check_records(self.state)['blockers'])
        self.draft('WRONG revised RIGHT', 'v2')
        self.assertIn('outside_edit_span_changed', wr.check_records(self.state)['blockers'])

    def test_delivery_target_is_never_overwritten(self):
        self.ready()
        target = self.put('final.md', 'Do not overwrite')
        with self.assertRaises(wr.Invalid):
            wr.deliver(self.state, target)
        self.assertEqual(target.read_text(), 'Do not overwrite')

    def test_final_verification_rejects_different_text(self):
        self.ready()
        wrong = self.put('final.md', 'Not the reviewed version')
        self.assertIn('delivery_does_not_match_reviewed_draft', wr.check_records(self.state, wrong)['blockers'])

    def test_report_input_mutation_cannot_rewrite_stored_review(self):
        self.ready()
        body = self.review_body('comparison')
        wr.add_review(self.state, body)
        body['summary'] = 'Changed externally'
        self.assertNotEqual(self.state['reviews'][-1]['body']['summary'], body['summary'])

    def test_failed_transaction_does_not_save_partial_changes(self):
        self.start()
        before = (self.run / 'run.json').read_bytes()
        with self.assertRaises(wr.Invalid):
            with wr.session(self.run, write=True) as state:
                state['events'].append({'unfinished': True})
                raise wr.Invalid('Stop')
        self.assertEqual(before, (self.run / 'run.json').read_bytes())

    def test_cli_requires_explicit_lifecycle_for_registration_and_delivery(self):
        contract = self.put('contract.json', json.dumps(self.contract))
        script = str(SCRIPTS / 'writing_run.py')
        def cli(*args):
            return subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True)
        self.assertEqual(cli('init', self.run, '--contract', contract).returncode, 0)
        self.assertEqual(cli('prepare', self.run, '--reason', 'No character center').returncode, 2)
        draft = self.put('v1.md', '门响了。她把信藏在身后。')
        self.assertEqual(cli('draft', self.run, '--id', 'v1', '--file', draft).returncode, 2)
        self.assertEqual(cli('check', self.run).returncode, 2)
        result = cli('deliver', self.run, '--to', self.root / 'final.md')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--lifecycle-run', result.stderr)
        self.assertFalse((self.root / 'final.md').exists())


if __name__ == '__main__':
    unittest.main()
