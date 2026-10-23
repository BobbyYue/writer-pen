"""Synthetic orchestration tests, not actual model calls or literary-quality proof."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'
sys.path.insert(0, str(ROOT / 'scripts'))
TEXT = 'At the door she folded the letter.\nHe waited outside.'


class WriterWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / 'skill'
        # Use the real shared helper, never a substitute acceptance implementation.
        shutil.copytree(ROOT, self.skill, ignore=shutil.ignore_patterns('tests', '__pycache__', '*.pyc'))
        self.task = self.root / 'task'
        self.registry = self.root / 'registry.sqlite3'
        self.contract = dict(mode='create', goal='Write a credible choice', scope='this whole synthetic scene',
                             fiction='allowed', constraints=[], require_character=False,
                             character_exemption='Synthetic non-character fixture only')
        self.plan = dict(task='Synthetic wrapper exercise', genre='scene', domain='synthetic tests',
                         purpose=self.contract['goal'], scope=self.contract['scope'], language='en', format='text',
                         reader=dict(knowledge='Only the supplied scene', need='Read without author answers'),
                         authority=dict(status='confirmed', basis='Synthetic test', reference='Not real user acceptance'),
                         material=dict(mode='fiction', gaps=[]), literary_intent='Keep the choice legible without fixing its meaning',
                         writing_basis=dict(given=[], interpretations=[], choices=['Synthetic adjustable choice']),
                         working_title=dict(text='Synthetic scene', reason='Structural fixture provisional title'),
                         constraints=[], reading_path=[dict(id='whole', purpose='This entire synthetic scene')],
                         author_context_id='synthetic-author')
        self.request = self.root / 'request.json'

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2), encoding='utf-8')
        return path

    def call(self, command, *arguments, ok=True, task=None):
        result = subprocess.run([sys.executable, '-B', str(self.skill / 'scripts/writer.py'), command,
                                 str(task or self.task), *map(str, arguments)], capture_output=True, text=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        output = result.stdout if result.returncode == 0 else result.stderr
        return json.loads(output)

    def write_request(self, **fields):
        return self.put('request.json', dict(contract=self.contract, plan=self.plan, **fields))

    def start(self, **fields):
        self.write_request(**fields)
        result = self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry)
        self.flow = json.loads((self.task / 'workflow.json').read_text())
        self.life = Path(self.flow['paths']['lifecycle'])
        self.native = Path(self.flow['paths']['native'])
        self.pinned = Path(self.flow['runtime']['root'])
        return result

    def native_state(self):
        return json.loads((self.native / 'run.json').read_text())

    def life_state(self):
        return json.loads((self.life / 'lifecycle.json').read_text())

    def draft(self, name='v1', text=TEXT):
        manuscript = self.put(name + '.txt', text)
        unit = self.put(name + '.unit.json', dict(unit_id='whole', summary='Synthetic observation only',
                         observations=[dict(quote=text.splitlines()[0], reason='Exact quote wiring, not literary proof')]))
        return self.call('draft', '--id', name, '--file', manuscript, '--record', unit)

    def self_checks(self, name='v1', choice='adopt'):
        import literary_methods
        quote = self.native_state()['drafts'][-1]['text'].splitlines()[0]
        evidence = [dict(artifact='draft:' + name, quote=quote)]
        base = dict(draft_id='draft:' + name, coverage='full', summary='Synthetic schema exercise',
                    observations=[dict(claim='Synthetic coverage wiring only; a letter is folded',
                                       covers=list(literary_methods.check_names()), evidence=evidence)], issues=[])
        clean = self.put(name + '.clean.json', dict(base, phase='clean'))
        comparison = self.put(name + '.comparison.json', dict(base, phase='comparison', comparisons=[]))
        self.call('self-review', '--clean', clean, '--comparison', comparison)
        decision = self.put(name + '.decision.json', dict(draft_id='draft:' + name, choice=choice,
                             reason='Synthetic decision only', evidence=evidence))
        self.call('decide', '--file', decision)

    def prepared_draft(self):
        self.start()
        self.call('prepare', '--reason', 'Synthetic contract exemption')
        self.draft()
        self.self_checks()

    def candidate(self, layout=None):
        measured = self.call('candidate')
        self.assertEqual(measured['status'], 'assessment-required')
        report = json.loads(Path(measured['report']).read_text())
        assessment = dict(text_sha256=report['text_sha256'],
                          report_sha256=hashlib.sha256(Path(measured['report']).read_bytes()).hexdigest(),
                          observations=[dict(metrics=list(report['metrics']), quote=TEXT.splitlines()[0],
                                             reason='Synthetic structural fixture, not metric-specific judgment')],
                          dispositions=[dict(signal_id=s['id'], decision='retain', reason='Synthetic signal fixture')
                                        for m in report['metrics'].values() for s in m['signals']],
                          not_applicable={}, issues=[])
        if layout:
            assessment['layout'] = layout
        self.assessment = self.put('assessment-' + str(len(self.life_state()['rounds']) + 1) + '.json', assessment)
        return self.call('candidate', '--assessment', self.assessment)

    def in_pinned(self, code, *arguments):
        bootstrap = 'import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);\n'
        result = subprocess.run([sys.executable, '-B', '-c', bootstrap + code, str(TESTS),
                                 str(self.pinned / 'scripts'), *map(str, arguments)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def seed_reviews(self, editorial=False, fail=False, suggestions=False):
        # This existing fixture creates synthetic process records only. No host is invoked.
        self.in_pinned('''
import json
from pathlib import Path
import writing_execution as e
import writing_lifecycle as l
import review_findings
from context_fixture import structural_context, structural_attribution, structural_reading, structural_development
from execution_fixture import seed_fixture
life = Path(sys.argv[3])
editorial, fail, suggestions = [v == 'True' for v in sys.argv[4:7]]
with l.session(life) as state:
    batch = state['rounds'][-1]
    text = state['candidates'][-1]['text']
    source = '\\n'.join(l.text(s['path']) for s in state['sources'])
records = []
for role in ('professional', 'reader'):
    issues = [dict(impact='Synthetic blocker', reason='Fixture only')] if fail and role == 'reader' else []
    draft_id = json.loads((life.parent / 'native/run.json').read_text())['drafts'][-1]['id']
    body = dict(draft_id=draft_id, role=role, context_id='synthetic-' + role + '-' + str(batch['round']),
                packet_sha256=batch['packets'][role]['sha256'], verdict='fail' if issues else 'pass',
                summary='Synthetic reviewer return; not a real review',
                evidence=[dict(quote=text.splitlines()[0], reason='Synthetic exact quote')], issues=issues)
    if role == 'professional':
        packet = l.load_json(batch['packets'][role]['path'])
        body['development_response'] = structural_development(text, review_findings.baselines_from_packet(packet))
        body['context_review'] = structural_context(text, 'literary')
        body['source_attribution'] = structural_attribution(text, source, 'source', 'literary')
    else:
        body['attribution_replay'] = structural_attribution(text, profile='literary')
        body['reading_response'] = structural_reading(text)
        finding = dict(id='E1', quote=text.splitlines()[0], impact='Two readings remain possible', reason='Synthetic author choice')
        if editorial:
            body['editorial'] = [finding]
        if suggestions:
            body['suggestions'] = [dict(finding, id='S1')]
    records.append(body)
aggregate = life / ('synthetic-aggregate-' + str(batch['round']) + '.json')
l.write_json(aggregate, dict(reviewer_records=records))
seed_fixture(life, aggregate)
''', self.life, editorial, fail, suggestions)

    def choice(self, choice='retain'):
        from context_fixture import structural_trial
        pending = self.call('finish-review')['pending_editorial'][0]
        path = self.put('author-choice.json', dict(pending, choice=choice, reason='Synthetic supported author choice',
                        trial=structural_trial(TEXT),
                        evidence=[dict(artifact='draft:v1', quote=TEXT.splitlines()[0])]))
        return self.call('author-choice', '--file', path)

    def test_start_pins_real_runtime_before_native_initialization(self):
        result = self.start()
        self.assertEqual(result['status'], 'initialized')
        self.assertNotEqual(self.pinned, self.skill)
        self.assertEqual(self.life_state()['profile'], 'literary')
        self.assertEqual(self.life_state()['units'], [])
        self.assertEqual(self.life_state()['execution']['task_id'], 'STABLE-SYNTHETIC')
        self.assertEqual(self.native_state()['drafts'], [])
        self.assertEqual(self.life_state()['implementation']['config']['path'], str(self.pinned / 'config/writing-quality.json'))
        self.assertNotIn('rounds', self.flow)
        self.assertNotIn('status', self.flow)

    def test_missing_or_empty_working_title_is_rejected_before_records(self):
        for title in (None, {}, dict(text='', reason='Synthetic fixture'),
                      dict(text='Synthetic scene', reason='')):
            with self.subTest(title=title):
                self.plan['working_title'] = title
                self.write_request()
                self.assertIn('working_title', self.call('start', '--request', self.request,
                              '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry, ok=False)['reason'])
                self.assertFalse((self.task / 'native').exists())

    def test_explicit_untitled_request_can_be_registered(self):
        self.plan['working_title'] = dict(text=None, reason='Explicit synthetic request for an untitled fragment')
        self.assertEqual(self.start()['status'], 'initialized')

    def test_start_resume_does_not_reset_native_or_registry(self):
        self.prepared_draft()
        before = (self.native / 'run.json').read_bytes()
        self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry)
        self.assertEqual((self.native / 'run.json').read_bytes(), before)
        self.assertEqual(len(self.life_state()['units']), 1)

    def test_plan_goal_scope_constraints_and_fiction_mismatch_fail_before_records(self):
        for field, value in (('purpose', 'Another goal'), ('scope', 'Another chapter'), ('constraints', ['New condition'])):
            with self.subTest(field=field):
                original = self.plan[field]
                self.plan[field] = value
                self.write_request()
                self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry, ok=False)
                self.assertFalse((self.task / 'native').exists())
                self.plan[field] = original
        self.contract['fiction'] = 'not_allowed'
        self.write_request()
        self.assertIn('fiction', self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC',
                                         '--registry', self.registry, ok=False)['reason'])

    def test_snapshot_preserves_exact_sources_and_survives_original_change(self):
        original = self.put('source.txt', 'Original designated scene.\n')
        extra = self.put('notes.txt', 'Additional source material.\n')
        self.start(sources=[str(original), str(extra)])
        snapshots = self.flow['sources']
        self.assertEqual(Path(snapshots[0]['snapshot']['path']).read_bytes(), original.read_bytes())
        self.assertEqual(self.native_state()['source']['origin'], snapshots[0]['snapshot']['path'])
        self.assertEqual([r['path'] for r in self.life_state()['sources']], [s['snapshot']['path'] for s in snapshots])
        original.write_text('Changed outside the task', encoding='utf-8')
        self.assertEqual(self.call('status')['status'], 'in-progress')
        self.assertEqual(Path(snapshots[0]['snapshot']['path']).stat().st_mode & 0o222, 0)

    def test_changed_snapshot_blocks_without_rehashing_records(self):
        original = self.put('source.txt', 'Designated scene.')
        self.start(source=str(original))
        path = Path(self.flow['sources'][0]['snapshot']['path'])
        before = (self.life / 'lifecycle.json').read_bytes()
        path.chmod(0o600)
        path.write_text('Changed snapshot', encoding='utf-8')
        self.assertIn('snapshot changed', self.call('status', ok=False)['reason'])
        self.assertEqual((self.life / 'lifecycle.json').read_bytes(), before)

    def test_dispatch_uses_pinned_native_after_canonical_edit(self):
        self.start()
        (self.skill / 'scripts/writing_run.py').write_text('raise RuntimeError("canonical must not run")\n')
        self.assertEqual(self.call('status')['status'], 'in-progress')
        self.call('prepare', '--reason', 'Use pinned APIs')
        self.assertEqual(len(self.native_state()['preparations']), 1)

    def test_changed_pinned_runtime_is_rejected(self):
        self.start()
        with (self.pinned / 'scripts/writing_run.py').open('a') as handle:
            handle.write('\n# changed pinned bytes\n')
        self.assertIn('Pinned runtime files changed', self.call('status', ok=False)['reason'])

    def test_partial_start_resumes_missing_native_and_execution_only(self):
        self.start()
        # Synthetic interruption after lifecycle init but before native init/execution link.
        shutil.rmtree(self.native)
        self.in_pinned('''
import writing_lifecycle as l
with l.session(sys.argv[3], True) as state:
    state.pop('execution')
''', self.life)
        before = self.life_state()['events']
        self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry)
        self.assertTrue((self.native / 'run.json').exists())
        self.assertEqual(self.life_state()['events'], before)
        self.assertEqual(self.life_state()['units'], [])

    def test_incomplete_native_directory_is_not_deleted(self):
        self.start()
        (self.native / 'run.json').unlink()
        marker = self.native / 'private-marker.txt'
        marker.write_text('Preserve partial work')
        result = self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry, ok=False)
        self.assertIn('Incomplete native directory', result['reason'])
        self.assertEqual(marker.read_text(), 'Preserve partial work')
        self.assertTrue(self.registry.exists())

    def test_orphan_runtime_reports_incomplete_without_repin_or_delete(self):
        self.task.mkdir()
        orphan = self.task / '_runtime'
        orphan.mkdir()
        self.write_request()
        result = self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry, ok=False)
        self.assertIn('Incomplete start', result['reason'])
        self.assertTrue(orphan.exists())

    def test_stable_id_cannot_move_to_another_directory(self):
        self.start()
        other = self.root / 'other-task'
        result = self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry,
                           task=other, ok=False)
        self.assertIn('already owns another run', result['reason'])
        self.assertTrue((other / 'workflow.json').exists())
        self.assertEqual(self.life_state()['units'], [])

    def test_changed_request_or_task_id_cannot_replace_contract(self):
        self.start()
        before = (self.native / 'run.json').read_bytes()
        self.call('start', '--request', self.request, '--task-id', 'DIFFERENT', '--registry', self.registry, ok=False)
        self.plan['purpose'] = 'Changed purpose'
        self.write_request()
        self.call('start', '--request', self.request, '--task-id', 'STABLE-SYNTHETIC', '--registry', self.registry, ok=False)
        self.assertEqual((self.native / 'run.json').read_bytes(), before)

    def test_character_is_sealed_before_draft_and_cannot_be_replaced(self):
        self.contract.update(require_character=True)
        self.contract.pop('character_exemption')
        self.start()
        result = self.call('prepare', '--reason', 'Missing character', ok=False)
        self.assertIn('Seal character', result['reason'])
        notes = self.put('people.md', 'Synthetic character: avoids a confrontation to protect a neighbor.')
        self.call('prepare', '--character', notes, '--id', 'people-v1', '--reason', 'Synthetic prewrite baseline')
        self.draft()
        state = self.native_state()
        self.assertTrue(state['drafts'][0]['character_id'])
        record = Path(state['characters'][0]['record_path'])
        before = record.read_bytes()
        notes.write_text('Changed character interpretation')
        self.call('prepare', '--character', notes, '--id', 'people-v1', '--reason', 'Must use another version', ok=False)
        self.assertEqual(record.read_bytes(), before)

    def test_draft_requires_preparation_before_any_unit(self):
        self.start()
        manuscript = self.put('draft.txt', TEXT)
        unit = self.put('unit.json', dict(unit_id='whole', summary='Fixture', observations=[dict(quote='letter', reason='Fixture')]))
        self.call('draft', '--id', 'v1', '--file', manuscript, '--record', unit, ok=False)
        self.assertEqual(self.life_state()['units'], [])

    def test_single_unit_draft_uses_actual_file_and_rejects_invented_quote(self):
        self.start()
        self.call('prepare', '--reason', 'Synthetic exemption')
        self.draft()
        self.assertEqual(self.life_state()['units'][0]['text'], TEXT)
        self.assertEqual(self.native_state()['drafts'][0]['text'], TEXT)
        unit = self.put('invalid-unit.json', dict(unit_id='whole', summary='Fixture',
                                                observations=[dict(quote='Never present', reason='Fixture')]))
        self.call('draft', '--id', 'v2', '--file', self.root / 'v1.txt', '--record', unit, ok=False)
        self.assertEqual(len(self.native_state()['drafts']), 1)

    def test_multi_unit_plan_requires_explicit_actual_files(self):
        self.plan['reading_path'] = [dict(id='first', purpose='First scene'), dict(id='second', purpose='Second scene')]
        self.start()
        self.call('prepare', '--reason', 'Synthetic exemption')
        manuscript = self.put('draft.txt', TEXT)
        record = self.put('whole.json', dict(unit_id='first', summary='Fixture', observations=[dict(quote='letter', reason='Fixture')]))
        self.call('draft', '--id', 'v1', '--file', manuscript, '--record', record, ok=False)
        self.assertEqual(self.life_state()['units'], [])
        units = []
        for identifier, text in zip(('first', 'second'), TEXT.splitlines()):
            self.put(identifier + '.txt', text)
            self.put(identifier + '.json', dict(unit_id=identifier, summary='Synthetic observation',
                      observations=[dict(quote=text, reason='Synthetic exact quote')]))
            units.append(dict(text=identifier + '.txt', record=identifier + '.json'))
        self.call('draft', '--id', 'v1', '--file', manuscript, '--units', self.put('units.json', units))
        self.assertEqual(len(self.life_state()['units']), 2)

    def test_candidate_requires_self_reviews_and_current_decision(self):
        self.start()
        self.call('prepare', '--reason', 'Synthetic exemption')
        self.draft()
        self.assertIn('clean/comparison', self.call('candidate', ok=False)['reason'])
        self.assertEqual(self.life_state()['rounds'], [])

    def test_measure_does_not_fabricate_assessment_or_open_review(self):
        self.prepared_draft()
        measured = self.call('candidate')
        self.assertEqual(measured['status'], 'assessment-required')
        self.assertEqual(json.loads(Path(measured['assessment_template']).read_text())['observations'], [])
        self.call('candidate', '--assessment', measured['assessment_template'], ok=False)
        self.assertEqual(self.life_state()['rounds'], [])

    def test_candidate_returns_pinned_bridge_and_retry_reuses_same_round(self):
        self.prepared_draft()
        result = self.candidate()
        self.assertEqual(result['status'], 'review-required')
        self.assertEqual(result['host_bridge']['options']['skillRoot'], str(self.pinned))
        reader = json.loads(Path(json.loads(Path(result['packets']).read_text())['reader']).read_text())
        self.assertNotIn('literary_intent', reader)
        self.assertNotIn('sources', reader)
        self.assertEqual(self.call('candidate')['round'], 1)
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertIsNone(self.life_state()['rounds'][0]['verdict'])

    def test_finish_without_real_or_fixture_captures_keeps_same_batch_open(self):
        self.prepared_draft()
        self.candidate()
        result = self.call('finish-review', ok=False)
        self.assertIn('captures are incomplete', result['reason'])
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertIsNone(self.life_state()['rounds'][0]['verdict'])
        self.assertNotIn('reviewer_records', self.native_state())

    def test_pending_editorial_imports_returns_then_resumes_after_author_choice(self):
        self.prepared_draft()
        self.candidate()
        self.seed_reviews(editorial=True)
        result = self.call('finish-review')
        self.assertEqual(result['status'], 'pending-editorial')
        self.assertEqual(len(self.native_state()['reviewer_records']), 2)
        self.assertIsNone(self.life_state()['rounds'][0]['verdict'])
        self.assertNotIn('review_results', self.native_state())
        self.assertIn('author-choice', self.call('status')['next'])
        self.assertTrue(self.choice()['resolved'])
        finished = self.call('finish-review')
        self.assertEqual(finished['verdict'], 'pass')
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertEqual(len(self.native_state()['reviewer_records']), 2)
        self.assertEqual(self.call('finish-review')['verdict'], 'pass')
        self.assertEqual(self.call('check')['status'], 'pass')

    def test_explicit_revise_closes_same_batch_as_fail_not_technical_retry(self):
        self.prepared_draft()
        self.candidate()
        self.seed_reviews(editorial=True)
        self.assertFalse(self.choice('revise')['resolved'])
        result = self.call('finish-review')
        self.assertEqual(result['verdict'], 'fail')
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertEqual(self.life_state()['rounds'][0]['verdict'], 'fail')
        self.call('deliver', '--to', self.root / 'not-final.txt', ok=False)
        self.assertFalse((self.root / 'not-final.txt').exists())

    def test_legacy_issues_cannot_be_waived_by_editorial_choice(self):
        self.prepared_draft()
        self.candidate()
        self.seed_reviews(editorial=True, fail=True)
        self.choice()
        self.assertEqual(self.call('finish-review')['verdict'], 'fail')
        self.assertEqual(self.life_state()['rounds'][0]['issues'][0]['impact'], 'Synthetic blocker')
        self.call('check', ok=False)

    def test_suggestions_do_not_require_author_choice(self):
        self.prepared_draft()
        self.candidate()
        self.seed_reviews(suggestions=True)
        self.assertEqual(self.call('finish-review')['verdict'], 'pass')
        self.assertNotIn('editorial_decisions', self.native_state())

    def test_status_never_promotes_existing_records_to_final_acceptance(self):
        self.prepared_draft()
        result = self.call('status')
        self.assertEqual(result['status'], 'in-progress')
        self.assertFalse(result['completion_verified'])
        self.call('check', ok=False)
        self.call('deliver', '--to', self.root / 'not-final.txt', ok=False)
        self.assertFalse((self.root / 'not-final.txt').exists())

    def test_three_round_limit_keeps_last_failure_visible_and_requires_explicit_draft(self):
        self.prepared_draft()
        for number in range(1, 4):
            if number > 1:
                self.draft('v' + str(number))
                self.self_checks('v' + str(number))
            self.candidate()
            self.seed_reviews(fail=number == 3)
            self.call('finish-review')
        self.assertEqual(len(self.life_state()['rounds']), 3)
        self.assertEqual([r['verdict'] for r in self.life_state()['rounds']], ['pass', 'pass', 'fail'])
        self.assertEqual(self.call('candidate')['status'], 'review-already-recorded')
        self.call('deliver', '--to', self.root / 'complete.txt', ok=False)
        result = self.call('deliver', '--draft', '--to', self.root / 'incomplete.txt')
        self.assertEqual(result['status'], 'review-incomplete-draft')
        self.assertTrue(Path(result['notice_path']).exists())
        self.assertFalse(result['lifecycle']['external_action_authorized'])
        self.draft('v4')
        self.self_checks('v4', choice='defer')
        measured = self.call('candidate')
        report = json.loads(Path(measured['report']).read_text())
        old = json.loads(self.assessment.read_text())
        old['text_sha256'] = report['text_sha256']
        old['report_sha256'] = hashlib.sha256(Path(measured['report']).read_bytes()).hexdigest()
        assessment = self.put('fourth-assessment.json', old)
        result = self.call('candidate', '--assessment', assessment, ok=False)
        self.assertIn('Review limit reached', result['reason'])
        self.assertEqual(len(self.life_state()['rounds']), 3)

    def test_candidate_retries_do_not_reset_host_technical_attempts(self):
        self.prepared_draft()
        candidate = self.candidate()
        self.in_pinned('''
import writing_execution as e
import writing_host as h
packets = e.load(sys.argv[4])
h.prepare(sys.argv[3], packets, sys.argv[5])
with e.task(sys.argv[3], True) as task:
    for job in task['batches']['1']['jobs'].values():
        job.update(status='blocked', attempts=e.policy()['max_technical_attempts'])
''', self.life, candidate['packets'], self.native)
        self.assertEqual(self.call('candidate')['round'], 1)
        result = subprocess.run([sys.executable, '-B', str(self.pinned / 'scripts/writing_host.py'),
                                 'prepare', str(self.life), '--packets', candidate['packets'],
                                 '--native-run', str(self.native)], text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertIsNone(self.life_state()['rounds'][0]['verdict'])

    def test_presentation_uses_native_api_without_new_round_and_blocks_changed_effect(self):
        self.plan['format'] = 'html'
        # A line break inside one paragraph must retain the exact manuscript bytes.
        html = self.put('scene.html', '<!doctype html><html><body><section data-writer-work>'
                        '<div data-writer-body><p>' + TEXT.replace('\n', '<br>') + '</p></div></section></body></html>')
        browser = self.put('browser-evidence.json', dict(synthetic=True, warning='Not a real browser inspection'))
        layout = dict(html=str(html), status='inspected', reason='Synthetic evidence binding only',
                      target='Synthetic HTML fixture', viewport='Synthetic desktop/mobile/print',
                      findings='Fixture only, not actual visual inspection', evidence_files=[str(html), str(browser)],
                      reading_observation=dict(quote=TEXT.splitlines()[0], status='fit',
                          observation='Synthetic rendered-reading fixture only; not an actual page inspection'),
                      reading_effect='unchanged', reading_reason='Synthetic unchanged-effect declaration')
        self.prepared_draft()
        self.candidate(layout=layout)
        self.seed_reviews()
        self.call('finish-review')
        result = self.call('presentation', '--record', self.put('layout.json', layout))
        self.assertEqual(result['new_semantic_rounds'], 0)
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertEqual(self.call('check')['status'], 'pass')
        layout['reading_effect'] = 'uncertain'
        result = self.call('presentation', '--record', self.put('layout-uncertain.json', layout))
        self.assertEqual(result['status'], 'literary-recheck-required')
        self.assertEqual(len(self.life_state()['rounds']), 1)
        self.assertIn('uncertain presentation', self.call('status')['next'])
        self.call('check', ok=False)

    def test_checked_exit_verifies_capture_and_never_overwrites(self):
        self.prepared_draft()
        self.candidate()
        self.seed_reviews()
        self.call('finish-review')
        existing = self.put('existing.txt', 'Keep this original')
        self.call('deliver', '--to', existing, ok=False)
        self.assertEqual(existing.read_text(), 'Keep this original')
        final = self.root / 'final.txt'
        result = self.call('deliver', '--to', final)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(final.read_bytes(), TEXT.encode())
        self.assertEqual(result['managed_execution']['status'], 'managed')
        capture = next((self.life / 'synthetic-capture').rglob('events.jsonl'))
        capture.write_text('Changed synthetic events')
        self.call('check', ok=False)
        self.call('deliver', '--to', self.root / 'after-drift.txt', ok=False)
        self.assertFalse((self.root / 'after-drift.txt').exists())


if __name__ == '__main__':
    unittest.main()
