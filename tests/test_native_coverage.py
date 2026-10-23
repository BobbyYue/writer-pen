"""Synthetic native coverage/closure checks, not literary or human review evidence."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from test_writing_run import WritingFixtures, literary_methods, wr
from context_fixture import structural_trial
import test_lifecycle_guard as guard
import writing_lifecycle as lifecycle


class CleanCoverageTests(WritingFixtures, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.start()
        self.prepare()
        self.draft()

    def test_one_observation_can_cover_all_authoritative_families(self):
        body = self.review_body()
        wr.add_review(self.state, body)
        self.assertEqual(len(body['observations']), 1)
        self.assertEqual(set(body['observations'][0]['covers']), set(literary_methods.check_names()))

    def test_shared_observations_can_cover_overlapping_families(self):
        body = self.review_body()
        names = list(literary_methods.check_names())
        observation = body['observations'][0]
        body['observations'] = [dict(observation, covers=names[:4]), dict(observation, covers=names[3:])]
        wr.add_review(self.state, body)

    def test_missing_unknown_duplicate_or_malformed_covers_is_rejected(self):
        names = list(literary_methods.check_names())
        for covers in (None, [], names[:-1], 'all', [None], [{}], names + ['invented'], names + names[:1]):
            body = self.review_body()
            body['observations'][0]['covers'] = covers
            with self.subTest(covers=covers), self.assertRaises(wr.Invalid):
                wr.add_review(self.state, body)
        body = self.review_body()
        del body['observations'][0]['covers']
        with self.assertRaisesRegex(wr.Invalid, 'covers'):
            wr.add_review(self.state, body)
        self.assertEqual(self.state['reviews'], [])

    def test_comparison_does_not_require_duplicate_family_narratives(self):
        wr.add_review(self.state, self.review_body())
        body = self.review_body('comparison')
        del body['observations'][0]['covers']
        wr.add_review(self.state, body)
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_checked_records_reject_legacy_clean_coverage_omission(self):
        self.reviewed()
        wr.decide(self.state, self.choice())
        del self.state['reviews'][0]['body']['observations'][0]['covers']
        self.assertTrue(any(b.startswith('clean_review_coverage:')
                            for b in wr.check_records(self.state)['blockers']))


class OpeningCoverageTests(WritingFixtures, unittest.TestCase):
    def test_separated_title_and_partial_title_prefixes_are_not_body_openings(self):
        source = 'Working title\n\nA body fragment.\n\nAnother paragraph.'
        for opening in ('W', 'Working title', 'Working title\n', 'Working title\n\n'):
            contract = dict(self.contract, mode='revise', source_title='Working title', opening_text=opening)
            with self.subTest(opening=opening), self.assertRaisesRegex(wr.Invalid, 'extend beyond'):
                wr.validate_contract(contract, wr.artifact('source', source))

    def test_title_plus_actual_fragment_is_valid_without_sentence_quota(self):
        source = 'Working title\n\nA body fragment.'
        wr.validate_contract(dict(self.contract, mode='revise', source_title='Working title', opening_text='Working title\n\nA'),
                             wr.artifact('source', source))

    def test_unseparated_and_multiline_fragments_remain_valid(self):
        for source, opening in (('An unfinished fragment', 'An'),
                                ('One\ncontinued fragment', 'One'),
                                ('One\ncontinued fragment\n\nNext', 'One'),
                                ('A title\n\n', 'A')):
            with self.subTest(source=source):
                wr.validate_contract(dict(self.contract, mode='revise', source_title=None, opening_text=opening),
                                     wr.artifact('source', source))

    def test_crlf_title_boundary_also_requires_body_text(self):
        source = 'Title\r\n\r\nBody fragment'
        for opening in ('Title', 'Title\r\n\r\n'):
            with self.subTest(opening=opening), self.assertRaisesRegex(wr.Invalid, 'extend beyond'):
                wr.validate_contract(dict(self.contract, mode='revise', source_title='Title', opening_text=opening),
                                     wr.artifact('source', source))
        wr.validate_contract(dict(self.contract, mode='revise', source_title='Title', opening_text='Title\r\n\r\nB'),
                             wr.artifact('source', source))

    def test_same_title_changed_body_requires_opening_comparison(self):
        source = 'Title\n\nOld opening.\n\nLast paragraph.'
        self.start(source=source, mode='revise', source_title='Title', opening_text='Title\n\nOld opening.')
        self.prepare()
        self.draft('Title\n\nNew opening.\n\nLast paragraph.')
        wr.add_review(self.state, self.review_body())
        comparison = self.review_body('comparison')
        comparison['comparisons'][0]['kind'] = 'other'
        with self.assertRaisesRegex(wr.Invalid, 'opening comparison'):
            wr.add_review(self.state, comparison)
        comparison['comparisons'][0]['kind'] = 'opening'
        wr.add_review(self.state, comparison)

    def test_untitled_one_line_first_paragraph_is_not_mistaken_for_a_title(self):
        source = '\u95e8\u54cd\u4e86\u3002\n\n\u5979\u628a\u4fe1\u85cf\u8d77\u6765\u3002'
        self.start(source=source, mode='revise', source_title=None, opening_text='\u95e8\u54cd\u4e86\u3002')
        self.prepare()
        self.draft(source)
        self.reviewed()
        wr.decide(self.state, self.choice('retain'))
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_revision_requires_explicit_source_title_boundary(self):
        source = wr.artifact('source', 'Title\n\nBody fragment.')
        contract = dict(self.contract, mode='revise', opening_text=source['text'])
        with self.assertRaisesRegex(wr.Invalid, 'Declare source_title'):
            wr.validate_contract(contract, source)

    def test_source_title_rejects_empty_nontext_and_multiline_values(self):
        source = wr.artifact('source', 'Title\n\nBody fragment.')
        for title in ('', ' ', False, 1, [], {}, 'Title\n', 'Title\r'):
            with self.subTest(title=title), self.assertRaisesRegex(wr.Invalid, 'source_title'):
                wr.validate_contract(dict(self.contract, mode='revise', source_title=title,
                                          opening_text=source['text']), source)

    def test_declared_source_title_needs_exact_first_line_and_real_separator(self):
        for title, source in (('Other title', 'Title\n\nBody fragment.'),
                              ('Tit', 'Title\n\nBody fragment.'),
                              ('Title', 'Title\nBody fragment.'),
                              ('Title', 'Preface\nTitle\n\nBody fragment.')):
            with self.subTest(title=title, source=source), self.assertRaisesRegex(wr.Invalid, 'exact first line'):
                wr.validate_contract(dict(self.contract, mode='revise', source_title=title, opening_text=source),
                                     wr.artifact('source', source))

    def test_declared_title_is_literal_not_a_pattern(self):
        source = 'Who [is it]?\n\nA body fragment.'
        wr.validate_contract(dict(self.contract, mode='revise', source_title='Who [is it]?',
                                  opening_text='Who [is it]?\n\nA'), wr.artifact('source', source))


class HistoricalFindingTests(WritingFixtures, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ready()

    def original_return(self, category='editorial', role='professional', legacy=False):
        draft = wr.current(self.state)
        finding = dict(id='same-id', quote=draft['text'], impact='Synthetic actionable concern',
                       reason='Fixture only, not an actual editorial judgment')
        if legacy:
            finding = dict(impact='Synthetic legacy blocker with overall review evidence')
        body = dict(role=role, context_id='synthetic-' + role, packet_sha256='synthetic-packet',
                    verdict='fail' if category == 'issues' else 'pass',
                    summary='Synthetic original return', evidence=[dict(quote=draft['text'], reason='Fixture')],
                    issues=[])
        body[category] = [finding]
        path = self.put(role + '-' + category + '.json', json.dumps(body))
        record = dict(draft_id=draft['id'], sha256=draft['sha256'], body=body,
                      result_path=str(path), result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.state.setdefault('reviewer_records', []).append(record)
        return record

    def next_draft(self, text=None, name='v2'):
        self.draft(text or (wr.current(self.state)['text'] + '\nA synthetic later observation.'), name)
        wr.add_review(self.state, self.review_body())

    def resolution(self, identifier, outcome='fixed', **changes):
        value = dict(issue=identifier, outcome=outcome, reason='Synthetic current-draft reassessment',
                     evidence=[self.cite()])
        value.update(changes)
        return value

    def test_old_actionable_finding_stays_bound_until_current_resolution(self):
        record = self.original_return()
        raw = copy.deepcopy(record)
        self.next_draft()
        indexed = wr.issue_index(self.state)
        self.assertEqual(len(indexed), 1)
        identifier, issue = next(iter(indexed.items()))
        self.assertEqual(issue['reviewer_binding'], wr.editorial_binding(record))
        self.assertIn('unresolved_issue:' + identifier, wr.blockers(self.state, require_decision=False))
        self.draft(wr.current(self.state)['text'] + '\nStill synthetic.', 'v3')
        self.assertEqual(list(wr.issue_index(self.state)), [identifier])
        self.assertEqual(record, raw)
        self.assertEqual(wr.read_json(record['result_path']), raw['body'])

    def test_removed_old_passage_can_be_fixed_with_current_evidence(self):
        record = self.original_return('issues')
        self.next_draft('A replacement scene, not the old passage.')
        identifier = next(iter(wr.issue_index(self.state)))
        self.assertNotIn(record['body']['evidence'][0]['quote'], wr.current(self.state)['text'])
        wr.add_review(self.state, self.review_body('comparison', resolutions=[self.resolution(identifier)]))
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.check_records(self.state)['status'], 'record_checks_satisfied')

    def test_resolution_cannot_use_only_old_draft_evidence(self):
        self.original_return('issues')
        self.next_draft()
        identifier = next(iter(wr.issue_index(self.state)))
        resolution = self.resolution(identifier, evidence=[self.cite('draft:v1')])
        with self.assertRaisesRegex(wr.Invalid, 'Evidence must cite'):
            wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))

    def test_unchanged_new_version_cannot_claim_fixed(self):
        self.original_return('issues')
        self.next_draft(wr.current(self.state)['text'])
        identifier = next(iter(wr.issue_index(self.state)))
        with self.assertRaisesRegex(wr.Invalid, 'Unchanged text'):
            wr.add_review(self.state, self.review_body('comparison', resolutions=[self.resolution(identifier)]))
        wr.add_review(self.state, self.review_body('comparison',
                     resolutions=[self.resolution(identifier, outcome='withdrawn')]))
        wr.decide(self.state, self.choice())

    def test_blocker_cannot_be_reclassified_as_an_accepted_preference(self):
        self.original_return('issues')
        self.next_draft()
        identifier = next(iter(wr.issue_index(self.state)))
        resolution = self.resolution(identifier, 'accepted_tradeoff',
                                     trial=structural_trial(wr.current(self.state)['text']))
        with self.assertRaisesRegex(wr.Invalid, 'Only an aesthetic'):
            wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))

    def test_retained_editorial_needs_actual_current_trial(self):
        self.original_return()
        self.next_draft()
        identifier = next(iter(wr.issue_index(self.state)))
        resolution = self.resolution(identifier, 'accepted_tradeoff')
        with self.assertRaisesRegex(wr.Invalid, 'trial'):
            wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        resolution['trial'] = structural_trial(wr.current(self.state)['text'])
        wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        wr.decide(self.state, self.choice())
        self.assertFalse(wr.check_records(self.state)['blockers'])

    def test_reworked_editorial_can_use_current_trial_without_old_quote(self):
        self.original_return()
        self.next_draft('A different passage retaining a chosen ambiguity.')
        identifier = next(iter(wr.issue_index(self.state)))
        resolution = self.resolution(identifier, 'accepted_tradeoff',
                                     trial=structural_trial(wr.current(self.state)['text']))
        wr.add_review(self.state, self.review_body('comparison', resolutions=[resolution]))
        wr.decide(self.state, self.choice())

    def test_old_resolution_does_not_claim_current_draft_was_rechecked(self):
        self.original_return('issues')
        self.next_draft()
        identifier = next(iter(wr.issue_index(self.state)))
        wr.add_review(self.state, self.review_body('comparison', resolutions=[self.resolution(identifier)]))
        self.next_draft(name='v3')
        wr.add_review(self.state, self.review_body('comparison'))
        self.assertIn('unresolved_issue:' + identifier, wr.check_records(self.state)['blockers'])

    def test_optional_suggestions_do_not_become_actionable_obligations(self):
        self.original_return('suggestions')
        self.next_draft()
        wr.add_review(self.state, self.review_body('comparison'))
        wr.decide(self.state, self.choice())
        self.assertEqual(wr.issue_index(self.state), {})
        self.assertFalse(wr.check_records(self.state)['blockers'])

    def test_role_and_receipt_distinguish_same_finding_ids(self):
        for role in ('professional', 'reader'):
            self.original_return(role=role)
        self.next_draft()
        indexed = wr.issue_index(self.state)
        self.assertEqual(len(indexed), 2)
        self.assertEqual({i['reviewer_binding']['role'] for i in indexed.values()}, {'professional', 'reader'})

    def test_legacy_blocker_without_id_or_own_quote_is_preserved(self):
        self.original_return('issues', legacy=True)
        self.next_draft()
        issue = next(iter(wr.issue_index(self.state).values()))
        self.assertTrue(issue['blocking'])
        self.assertEqual(issue['kind'], 'coherence')
        self.assertEqual(issue['evidence'][0]['artifact'], 'draft:v1')

    def test_changed_historical_return_is_not_silently_reinterpreted(self):
        record = self.original_return()
        self.next_draft()
        self.put('professional-editorial.json', '{}')
        with self.assertRaisesRegex(wr.Invalid, 'Historical native reviewer result changed'):
            wr.issue_index(self.state)
        self.assertEqual(record['body']['editorial'][0]['id'], 'same-id')


class NativeCoverageIntegrationTests(unittest.TestCase):
    def fixture(self, complete=False):
        fixture = guard.LifecycleGuardTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.linked(complete=complete)
        return fixture

    def test_new_pass_does_not_erase_old_findings_and_resolutions_preserve_rounds(self):
        f = self.fixture()
        f.begin_round()
        quote = wr.current(f.state)['text']
        f.reviewer('professional', verdict='fail', issues=[dict(id='B1', quote=quote,
                   impact='Synthetic blocker', reason='Original fixture concern')])
        f.reviewer('reader', editorial=[dict(id='E1', quote=quote,
                   impact='Synthetic artistic choice', reason='Original fixture choice')])
        originals = {r['result_path']: Path(r['result_path']).read_bytes() for r in f.state['reviewer_records']}
        f.finish_round(verdict='fail')
        path = f.put('v2.md', quote + '\nShe waited. Synthetic fixture only.')
        f.unit(path, suffix='2')
        wr.add_draft(f.state, 'v2', path, lifecycle_run=f.lifecycle, checkpoint='scene-1')
        f.reviewed()
        wr.decide(f.state, f.choice('defer'))
        f.begin_round('2')
        for role in ('professional', 'reader'):
            f.reviewer(role, filename=role + '-2.json', context_id=role + '-2')
        payload = wr.native_review_payload(f.state)
        self.assertEqual(payload['status'], 'fail')
        historical = wr.issue_index(f.state)
        self.assertEqual(len(historical), 2)
        for identifier in historical:
            self.assertTrue(any(identifier in item['impact'] for item in payload['issues']))
        forged = dict(payload, status='pass', issues=[])
        with self.assertRaises(wr.Invalid):
            wr.bind_review_result(f.state, f.put_json('omitted-history.json', forged))
        resolutions = [dict(issue=identifier, outcome='fixed' if issue['kind'] == 'coherence' else 'accepted_tradeoff',
                            reason='Synthetic explicit current-draft resolution, not quality proof', evidence=[f.cite()])
                       for identifier, issue in historical.items()]
        for resolution in resolutions:
            if resolution['outcome'] == 'accepted_tradeoff':
                resolution['trial'] = structural_trial(wr.current(f.state)['text'])
        wr.add_review(f.state, f.review_body('comparison', resolutions=resolutions))
        wr.decide(f.state, f.choice())
        f.finish_round('2')
        result = wr.deliver(f.state, f.root / 'final.txt', lifecycle_run=f.lifecycle)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['lifecycle']['rounds'], 2)
        for path, raw in originals.items():
            self.assertEqual(Path(path).read_bytes(), raw)

    def test_native_uses_authoritative_packet_baselines_even_without_native_source(self):
        f = self.fixture(complete=True)
        self.assertIsNone(f.state['source'])
        lifecycle.start_review(f.lifecycle, wr.current(f.state)['origin'])
        body = f.reviewer_body('professional', context_id='new-professional')
        anchors = body['development_response']['checks']['revision_effects']['baseline_evidence']
        self.assertEqual([a['id'] for a in anchors], ['source:1'])
        anchors.clear()
        with self.assertRaisesRegex(wr.Invalid, 'baseline_evidence'):
            wr.add_reviewer_record(f.state, body, f.put_json('omitted-baseline.json', body))

    def test_native_rejects_unknown_baseline_ids_from_a_bound_return(self):
        f = self.fixture(complete=True)
        lifecycle.start_review(f.lifecycle, wr.current(f.state)['origin'])
        body = f.reviewer_body('professional', context_id='new-professional')
        anchors = body['development_response']['checks']['revision_effects']['baseline_evidence']
        anchors.append(dict(anchors[0], id='invented:previous'))
        with self.assertRaisesRegex(wr.Invalid, 'baseline'):
            wr.add_reviewer_record(f.state, body, f.put_json('unknown-baseline.json', body))


if __name__ == '__main__':
    unittest.main()
