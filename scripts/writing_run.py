#!/usr/bin/env python3
"""Local writing records and version checks, not a literary-quality judge.

The CLI controls registration/review/export order, not model generation itself.
All text stays in the chosen local run directory. Records are not tamper-proof.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import context_value
import review_findings
import source_attribution

from character_record import verify as verify_character


class Invalid(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Invalid(message)


def nonempty(value, label):
    need(isinstance(value, str) and bool(value.strip()), label + ' must be nonempty text')
    return value


def array(value, label):
    need(isinstance(value, list), label + ' must be a list')
    return value


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read_text(filename):
    data = Path(filename).read_bytes().decode('utf-8')
    nonempty(data, str(filename))
    return data


def read_json(filename):
    data = json.loads(read_text(filename))
    need(isinstance(data, dict), 'Expected a JSON object')
    return data


def artifact(identifier, text, origin=None):
    return dict(id=identifier, text=text, sha256=digest(text), origin=origin)


def objects(state):
    items = ([state['source']] if state['source'] else [])
    items += state['characters'] + state['drafts']
    return {item['id']: item for item in items}


def current(state):
    need(bool(state['drafts']), 'Register a draft first')
    return state['drafts'][-1]


def validate_storage(state):
    need(state.get('format_version') == 1, 'Unsupported run format')
    for item in objects(state).values():
        need(digest(item['text']) == item['sha256'], 'Stored text changed: ' + item['id'])
    for person in state['characters']:
        verified = verify_character(person['record_path'])
        need(verified['sha256'] == person['sha256'], 'Character baseline changed')
    if state['source']:
        source = state['source']
        need(digest(read_text(source['origin'])) == source['sha256'],
             'Source changed since init; confirm the source and start a new run')


@contextmanager
def session(directory, write=False):
    root = Path(directory)
    need(root.is_dir() and not root.is_symlink(), 'Run directory is missing or is a symlink')
    path = root / 'run.json'
    need(path.is_file() and not path.is_symlink(), 'run.json is missing or is a symlink')
    lockpath = root / '.lock'
    fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = read_json(path)
        validate_storage(state)
        yield state
        if write:
            fd, temp = tempfile.mkstemp(prefix='.run-', suffix='.json', dir=root)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                    json.dump(state, handle, ensure_ascii=False, indent=2)
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)


def event(state, operation, reference):
    state['events'].append(dict(sequence=len(state['events']) + 1,
                                time=now(), operation=operation, reference=reference))


def validate_contract(contract, source):
    allowed = {'mode', 'goal', 'scope', 'fiction', 'constraints', 'require_character',
               'character_exemption', 'min_chars', 'max_chars', 'preserve_exact',
               'opening_text', 'source_title', 'edit_span'}
    need(not set(contract) - allowed, 'Unknown contract fields: ' + ', '.join(sorted(set(contract) - allowed)))
    need(contract.get('mode') in ('create', 'revise', 'local'), 'mode: create, revise or local')
    for name in ('goal', 'scope'):
        nonempty(contract.get(name), name)
    need(contract.get('fiction') in ('allowed', 'not_allowed', 'unspecified'), 'Declare fiction permission')
    need(type(contract.get('require_character')) is bool, 'Declare require_character as a boolean')
    if not contract['require_character']:
        nonempty(contract.get('character_exemption'), 'character_exemption')
    for text in array(contract.get('constraints', []), 'constraints'):
        nonempty(text, 'constraint')
    for key in ('min_chars', 'max_chars'):
        if key in contract:
            need(type(contract[key]) is int and contract[key] >= 0, key + ' must be a nonnegative integer')
    need(contract.get('max_chars', float('inf')) >= contract.get('min_chars', 0), 'Inverted character limits')
    for text in array(contract.get('preserve_exact', []), 'preserve_exact'):
        nonempty(text, 'preserved text')
    if contract['mode'] in ('revise', 'local'):
        need(source is not None, 'Revision requires the designated source file')
    if contract['mode'] == 'revise':
        opening = nonempty(contract.get('opening_text'), 'opening_text')
        need(source['text'].startswith(opening), 'opening_text must be an exact prefix of the source body')
        need('source_title' in contract, 'Declare source_title as the actual source title or null for untitled text')
        title = contract['source_title']
        if title is not None:
            nonempty(title, 'source_title')
            need('\n' not in title and '\r' not in title, 'source_title must be one exact title line')
            first = re.match(re.escape(title) + r'\r?\n[ \t]*\r?\n', source['text'])
            need(first is not None, 'source_title must match the exact first line followed by a blank separator')
            need(bool(opening[first.end():].strip()),
                 'opening_text must extend beyond a separated title into the body opening')
    if 'edit_span' in contract:
        span = contract['edit_span']
        need(source is not None and isinstance(span, list) and len(span) == 2
             and all(type(n) is int for n in span), 'edit_span needs [start, end] in the source')
        need(0 <= span[0] <= span[1] <= len(source['text']), 'edit_span is outside the source')


def init_run(directory, contract, source_path=None):
    source = artifact('source', read_text(source_path), str(Path(source_path).resolve())) if source_path else None
    validate_contract(contract, source)
    root = Path(directory)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    state = dict(format_version=1, contract=contract, source=source,
                 characters=[], preparations=[], drafts=[], reviews=[], decisions=[], events=[])
    event(state, 'init', 'source' if source else None)
    with (root / 'run.json').open('x', encoding='utf-8') as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    os.chmod(root / 'run.json', 0o600)
    return {'status': 'initialized', 'run': str(root.resolve())}


def lifecycle_location(state, run_path=None):
    selected = run_path or state.get('lifecycle_run')
    need(selected, 'lifecycle_run is required for full workflow checks')
    root = Path(selected)
    need(not root.is_symlink() and root.is_dir() and (root / 'lifecycle.json').is_file()
         and not (root / 'lifecycle.json').is_symlink(), 'Missing or unsafe lifecycle.json in lifecycle_run')
    root = root.resolve()
    linked = state.get('lifecycle_run')
    need(not linked or Path(linked).resolve() == root, 'lifecycle_run differs from the registered task')
    return str(root)


def lifecycle_registration(state, run_path, filename=None, checkpoint=None):
    lifecycle = importlib.import_module('writing_lifecycle')
    with lifecycle.session(run_path) as record:
        need(record['profile'] == 'literary', 'Writing profile must be literary')
        need(any(e['operation'] == 'prewrite' for e in record['events']), 'Writing prewrite record is missing')
        contract, plan = state['contract'], record['plan']
        need(plan['material']['mode'] != 'fiction' or contract['fiction'] == 'allowed',
             'Native fiction permission does not allow a fiction lifecycle')
        native_constraints = {text.strip() for text in array(contract.get('constraints', []), 'native constraints')}
        plan_constraints = {nonempty(text, 'lifecycle constraint').strip()
                            for text in array(plan.get('constraints'), 'lifecycle constraints')}
        need(native_constraints == plan_constraints, 'Lifecycle constraints differ from the native contract')
        # Compare explicit task fields, not inferred equivalence of prose or artistic intent.
        need(nonempty(plan.get('purpose'), 'lifecycle purpose').strip() == contract['goal'].strip(),
             'Lifecycle purpose must match the native goal')
        need(nonempty(plan.get('scope'), 'lifecycle scope').strip() == contract['scope'].strip(),
             'Lifecycle scope must match the native scope')
        if filename is not None:
            nonempty(checkpoint, 'lifecycle unit checkpoint')
            units = [u for u in record['units'] if u['unit_id'] == checkpoint]
            need(bool(units), 'Writing-in-progress unit checkpoint is missing')
            need(lifecycle.compact(units[-1]['text']) in lifecycle.compact(lifecycle.visible(filename)),
                 'Draft changed after unit checkpoint; record the affected unit again')


def prepare(state, record_path, reason, timing, *, lifecycle_run=None):
    nonempty(reason, 'preparation reason')
    need(timing in ('prewrite', 'during', 'retrospective'), 'Invalid preparation timing')
    need(record_path or not state['contract']['require_character'], 'Seal character analysis before preparation')
    linked = lifecycle_location(state, lifecycle_run) if lifecycle_run or state.get('lifecycle_run') else None
    if linked:
        lifecycle_registration(state, linked)
    person = None
    if record_path:
        result = verify_character(record_path)
        person = artifact('character:' + str(len(state['characters']) + 1), read_text(result['snapshot']))
        person['record_path'] = str(Path(record_path).resolve())
        state['characters'].append(person)
    preparation = dict(id=len(state['preparations']) + 1,
                       character_id=person['id'] if person else None, reason=reason, timing=timing)
    if linked:
        state['lifecycle_run'] = linked
        preparation['lifecycle_run'] = linked
    state['preparations'].append(preparation)
    event(state, 'prepare', preparation['id'])
    return preparation


def add_draft(state, name, filename, *, lifecycle_run=None, checkpoint=None):
    need(bool(state['preparations']), 'Prepare before registering a draft')
    need(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name)), 'Use a short safe draft id')
    identifier = 'draft:' + name
    need(identifier not in objects(state), 'Draft id already exists; use a new version')
    linked = lifecycle_location(state, lifecycle_run) if lifecycle_run or state.get('lifecycle_run') else None
    if linked:
        need(state['preparations'][-1].get('lifecycle_run') == linked,
             'Prepare with lifecycle_run before registering a linked draft')
        nonempty(checkpoint, 'lifecycle unit checkpoint')
        lifecycle_registration(state, linked, filename, checkpoint)
    item = artifact(identifier, read_text(filename), str(Path(filename).resolve()))
    item['preparation'] = state['preparations'][-1]['id']
    item['character_id'] = state['preparations'][-1]['character_id']
    if linked:
        item.update(lifecycle_run=linked, checkpoint=checkpoint)
    state['drafts'].append(item)
    event(state, 'draft', identifier)
    return {'draft_id': identifier, 'sha256': item['sha256'], 'next': 'clean review of this version'}


def evidence(state, entries, required=None):
    entries = array(entries, 'evidence')
    need(bool(entries), 'Evidence cannot be empty')
    cited = set()
    for item in entries:
        need(isinstance(item, dict), 'Evidence entry must be an object')
        target = objects(state).get(item.get('artifact'))
        need(target is not None, 'Unknown evidence artifact')
        quote = nonempty(item.get('quote'), 'quote')
        need(quote in target['text'], 'Quote not found in ' + target['id'])
        cited.add(target['id'])
    if required:
        need(set(required).issubset(cited), 'Evidence must cite: ' + ', '.join(sorted(required)))


def issue_index(state):
    result = {review['id'] + '/' + issue['id']: dict(issue, draft_id=review['draft_id'])
              for review in state['reviews'] for issue in review['body'].get('issues', [])}
    result.update(historical_reviewer_issues(state))
    return result


def historical_reviewer_issues(state):
    """Carry actionable original returns, not optional suggestions or new verdicts."""
    if not state['drafts']:
        return {}
    selected = final_reviewers(state)
    result = {}
    for record in state.get('reviewer_records', []):
        if selected.get(record['body']['role']) is record:
            continue
        original = objects(state).get(record['draft_id'])
        need(original and original['sha256'] == record['sha256'], 'Historical reviewer draft binding changed')
        path = Path(record['result_path'])
        need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record['result_sha256']
             and read_json(path) == record['body'], 'Historical native reviewer result changed')
        binding = editorial_binding(record)
        prefix = 'reviewer:' + digest(json.dumps(binding, sort_keys=True, ensure_ascii=False))
        for category in ('issues', 'editorial'):
            for index, finding in enumerate(record['body'].get(category, []), 1):
                quote = finding.get('quote')
                entries = ([dict(quote=quote)] if quote else record['body']['evidence'])
                anchors = [dict(artifact=original['id'], quote=entry['quote']) for entry in entries]
                evidence(state, anchors, [original['id']])
                identifier = prefix + '/' + category + '/' + str(index)
                result[identifier] = dict(
                    id=identifier, draft_id=original['id'], blocking=True,
                    kind='preference' if category == 'editorial' else
                         ('constraint' if finding.get('kind') == 'constraint' else 'coherence'),
                    claim=finding['impact'], reason=finding.get('reason', finding['impact']),
                    evidence=anchors, reviewer_binding=binding,
                    finding_id=finding.get('id'), finding_category=category)
    return result


def validate_clean_coverage(observations):
    import literary_methods
    required = set(literary_methods.check_names())
    covered = set()
    for observation in array(observations, 'observations'):
        need(isinstance(observation, dict), 'Observation must be an object')
        names = array(observation.get('covers'), 'Clean observation covers')
        need(all(isinstance(name, str) and name in required for name in names),
             'Clean observation covers must use authoritative literary check IDs')
        need(len(names) == len(set(names)), 'Clean observation covers contains duplicate IDs')
        covered.update(names)
    need(covered == required, 'Clean observations must cover all literary checks; missing: ' +
         ', '.join(sorted(required - covered)))


def latest_reviews(state):
    draft = current(state)
    result = {}
    for review in state['reviews']:
        if review['draft_id'] == draft['id'] and review['sha256'] == draft['sha256']:
            result[review['body']['phase']] = review
    return result


def add_review(state, body):
    body = json.loads(json.dumps(body))
    draft = current(state)
    need(body.get('draft_id') == draft['id'], 'Review is not for the current draft')
    phase = body.get('phase')
    need(phase in ('clean', 'comparison'), 'Review phase must be clean or comparison')
    expected_scope = 'excerpt' if state['contract']['mode'] == 'local' else 'full'
    need(body.get('coverage') == expected_scope, 'Review coverage must be ' + expected_scope)
    nonempty(body.get('summary'), 'review summary')
    observations = array(body.get('observations'), 'observations')
    need(bool(observations), 'Record at least one text-supported observation, not a pass stamp')
    if phase == 'clean':
        validate_clean_coverage(observations)
    for observation in observations:
        need(isinstance(observation, dict), 'Observation must be an object')
        nonempty(observation.get('claim'), 'observation claim')
        evidence(state, observation.get('evidence'), [draft['id']])
        if phase == 'clean':
            need(all(x['artifact'] == draft['id'] for x in observation['evidence']),
                 'Clean observations must cite only this draft')
    seen = set()
    for issue in array(body.get('issues', []), 'issues'):
        need(isinstance(issue, dict), 'Issue must be an object')
        identifier = nonempty(issue.get('id'), 'issue id')
        need(bool(re.fullmatch(r'[A-Za-z0-9_-]+', identifier)) and identifier not in seen, 'Invalid or duplicate issue id')
        seen.add(identifier)
        need(issue.get('kind') in ('constraint', 'coherence', 'preference'), 'Invalid issue kind')
        need(type(issue.get('blocking')) is bool, 'Declare issue blocking as a boolean')
        need(issue['kind'] != 'constraint' or issue['blocking'], 'A constraint issue cannot be advisory')
        nonempty(issue.get('claim'), 'issue claim')
        evidence(state, issue.get('evidence'), [draft['id']])
    known = issue_index(state)
    resolved_ids = set()
    for resolution in array(body.get('resolutions', []), 'resolutions'):
        need(isinstance(resolution, dict), 'Resolution must be an object')
        identifier = resolution.get('issue')
        need(identifier in known and identifier not in resolved_ids, 'Unknown or duplicate resolved issue')
        resolved_ids.add(identifier)
        issue = known[identifier]
        outcome = resolution.get('outcome')
        need(outcome in ('fixed', 'withdrawn', 'accepted_tradeoff'), 'Invalid resolution outcome')
        nonempty(resolution.get('reason'), 'resolution reason')
        evidence(state, resolution.get('evidence'), [draft['id']])
        if outcome == 'fixed':
            need(objects(state)[issue['draft_id']]['sha256'] != draft['sha256'],
                 'Unchanged text cannot be marked fixed; withdraw a mistaken finding with evidence')
        if outcome == 'accepted_tradeoff':
            need(issue['kind'] == 'preference', 'Only an aesthetic tradeoff can be accepted; fix or withdraw other findings')
            trial_errors = review_findings.validate_trial(resolution.get('trial'), draft['text'])
            need(not trial_errors, '; '.join(trial_errors))
            anchors = [e['quote'] for e in issue['evidence'] if e['artifact'] == issue['draft_id']
                       and e['quote'] in draft['text']]
            if not anchors and issue.get('reviewer_binding'):
                anchors = [e['quote'] for e in resolution['evidence'] if e['artifact'] == draft['id']]
            need(any(q in resolution['trial']['current'] for q in anchors),
                 'Tradeoff trial must cover the original issue passage still present, or its current resolution evidence')
    if phase == 'comparison':
        need('clean' in latest_reviews(state), 'Submit clean reading before comparison')
        baseline = draft['character_id']
        if baseline:
            character = body.get('character')
            need(isinstance(character, dict), 'Compare with this draft character baseline')
            need(character.get('outcome') in ('consistent', 'development', 'unsupported', 'not_expressed'),
                 'Invalid character outcome')
            nonempty(character.get('reason'), 'character reason')
            evidence(state, character.get('evidence'), [draft['id'], baseline])
            if character['outcome'] == 'development':
                record_path = nonempty(character.get('development_record'), 'development_record')
                result = verify_character(record_path)
                need(result['sha256'] != objects(state)[baseline]['sha256'],
                     'Development needs a new analysis, not the unchanged baseline')
                developed = artifact('character:' + str(len(state['characters']) + 1), read_text(result['snapshot']))
                developed['record_path'] = str(Path(record_path).resolve())
                state['characters'].append(developed)
                character['development_id'] = developed['id']
        comparisons = array(body.get('comparisons', []), 'comparisons')
        for comparison in comparisons:
            need(isinstance(comparison, dict), 'Comparison must be an object')
            need(comparison.get('kind') in ('opening', 'key_change', 'other'), 'Invalid comparison kind')
            before = comparison.get('before')
            need(before in objects(state) and (before == 'source' or before.startswith('draft:'))
                 and before != draft['id'], 'Comparison needs a source or earlier draft')
            for field in ('gain', 'loss', 'attention_cost', 'reason'):
                nonempty(comparison.get(field), field)
            need(comparison.get('choice') in ('adopt', 'retain', 'retry', 'defer'), 'Invalid comparison choice')
            evidence(state, comparison.get('evidence'), [before, draft['id']])
        source = state['source']
        if source and source['text'] != draft['text'] and state['contract']['mode'] in ('revise', 'local'):
            need(any(c['before'] == 'source' for c in comparisons), 'Changed revision needs source/candidate comparison')
        opening = state['contract'].get('opening_text')
        if opening and not draft['text'].startswith(opening):
            need(any(c['kind'] == 'opening' and c['before'] == 'source' for c in comparisons),
                 'Changed opening needs an opening comparison against source')
    identifier = 'review:' + str(len(state['reviews']) + 1)
    review = dict(id=identifier, draft_id=draft['id'], sha256=draft['sha256'], body=body)
    state['reviews'].append(review)
    event(state, 'review', identifier)
    return {'review_id': identifier, 'issues': [identifier + '/' + x['id'] for x in body.get('issues', [])]}


def blockers(state, require_decision=True, final=None):
    draft = current(state)
    reasons = []
    text = draft['text']
    contract = state['contract']
    if digest(read_text(draft['origin'])) != draft['sha256']:
        reasons.append('working_draft_changed: register it as a new version')
    if draft['preparation'] != state['preparations'][-1]['id']:
        reasons.append('preparation_changed: register and review a new draft version')
    count = len(''.join(text.split()))
    if count < contract.get('min_chars', 0) or count > contract.get('max_chars', float('inf')):
        reasons.append('character_limit: count is ' + str(count) + ' (non-whitespace Unicode characters)')
    for phrase in contract.get('preserve_exact', []):
        if phrase not in text:
            reasons.append('required_text_missing')
    if 'edit_span' in contract:
        source = state['source']['text']
        start, end = contract['edit_span']
        prefix, suffix = source[:start], source[end:]
        if len(text) < len(prefix) + len(suffix) or not text.startswith(prefix) or not text.endswith(suffix):
            reasons.append('outside_edit_span_changed')
    reviews = latest_reviews(state)
    for phase in ('clean', 'comparison'):
        if phase not in reviews:
            reasons.append('missing_' + phase + '_review_for_current_draft')
    if 'clean' in reviews:
        try:
            validate_clean_coverage(reviews['clean']['body'].get('observations'))
        except ValueError as error:
            reasons.append('clean_review_coverage:' + str(error))
    if all(p in reviews for p in ('clean', 'comparison')):
        order = [review['id'] for review in state['reviews']]
        if order.index(reviews['comparison']['id']) < order.index(reviews['clean']['id']):
            reasons.append('comparison_predates_latest_clean_review')
        if reviews['comparison']['body'].get('character', {}).get('outcome') == 'unsupported':
            reasons.append('unsupported_character_change')
        if any(item['choice'] in ('retry', 'defer') for item in reviews['comparison']['body'].get('comparisons', [])):
            reasons.append('comparison_not_decided')
    resolved = {item['issue'] for review in state['reviews'] if review['draft_id'] == draft['id']
                for item in review['body'].get('resolutions', [])}
    for identifier, issue in issue_index(state).items():
        if issue['blocking'] and identifier not in resolved:
            reasons.append('unresolved_issue:' + identifier)
    if require_decision:
        decisions = [d for d in state['decisions'] if d['draft_id'] == draft['id']]
        decision = decisions[-1] if decisions else None
        if not decision or decision['choice'] not in ('adopt', 'retain'):
            reasons.append('missing_final_choice')
        elif decision['review_ids'] != {phase: item['id'] for phase, item in reviews.items()}:
            reasons.append('decision_predates_latest_review')
    if final and digest(read_text(final)) != draft['sha256']:
        reasons.append('delivery_does_not_match_reviewed_draft')
    return reasons


def decide(state, body):
    body = json.loads(json.dumps(body))
    draft = current(state)
    need(body.get('draft_id') == draft['id'], 'Decision is not for the current draft')
    need(body.get('choice') in ('adopt', 'retain', 'retry', 'defer'), 'Invalid final choice')
    nonempty(body.get('reason'), 'decision reason')
    evidence(state, body.get('evidence'), [draft['id']])
    if body['choice'] == 'retain':
        need(state['source'] and state['source']['text'] == draft['text'], 'retain requires unchanged source text')
    if body['choice'] in ('adopt', 'retain'):
        reasons = blockers(state, require_decision=False)
        need(not reasons, '; '.join(reasons))
    decision = dict(body, review_ids={phase: item['id'] for phase, item in latest_reviews(state).items()})
    state['decisions'].append(decision)
    event(state, 'decide', len(state['decisions']))
    return {'choice': body['choice'], 'draft_id': draft['id']}


def check_records(state, final=None):
    """Check native local records only; this never authorizes final delivery."""
    reasons = blockers(state, final=final)
    draft = current(state)
    unresolved_advisory = [key for key, issue in issue_index(state).items() if not issue['blocking']
                          and not any(r['draft_id'] == draft['id'] and any(x['issue'] == key for x in r['body'].get('resolutions', []))
                                      for r in state['reviews'])]
    return dict(status='blocked' if reasons else 'record_checks_satisfied', blockers=reasons,
                draft_id=draft['id'], sha256=draft['sha256'], scope=state['contract']['scope'],
                non_whitespace_chars=len(''.join(draft['text'].split())),
                advisory_issues=unresolved_advisory, timing=state['preparations'][-1]['timing'],
                boundary='Native records only; no lifecycle completion, literary quality, or generation-order claim.')


def add_reviewer_record(state, body, result_path):
    """Register native final reviews without relabeling the writer's self-checks."""
    body = json.loads(json.dumps(body))
    draft = current(state)
    need(body.get('draft_id') == draft['id'], 'Reviewer record is not for the current draft')
    role = body.get('role')
    need(role in ('professional', 'reader'), 'Reviewer role must be professional or reader')
    context = nonempty(body.get('context_id'), 'fresh reviewer context_id')
    linked = lifecycle_location(state)
    lifecycle = importlib.import_module('writing_lifecycle')
    with lifecycle.session(linked) as run:
        need(run['profile'] == 'literary' and run['rounds'], 'Start a literary review batch first')
        batch = run['rounds'][-1]
        attribution_source = '\n'.join(lifecycle.text(s['path']) for s in run['sources'])
        need(batch['artifact_sha256'] == draft['sha256'], 'Reviewer packet belongs to another draft')
        need(body.get('packet_sha256') == batch['packets'][role]['sha256'],
             'Reviewer must bind the isolated input packet')
        lifecycle.verify_ref(batch['packets'][role])
        baselines = review_findings.baselines_from_packet(read_json(batch['packets'][role]['path']))
        need(context != run['plan'].get('author_context_id'), 'Author context cannot be an independent reviewer')
        need(all(context != r['context_id'] for old in run['rounds'][:-1] for r in old.get('reviewer_records', [])),
             'Use a fresh context for each review round')
    need(body.get('verdict') in ('pass', 'fail'), 'Reviewer verdict must be pass or fail')
    nonempty(body.get('summary'), 'reviewer summary')
    quotes = array(body.get('evidence'), 'reviewer evidence')
    need(bool(quotes), 'Reviewer needs evidence from the current body')
    for entry in quotes:
        need(isinstance(entry, dict), 'Reviewer evidence must be an object')
        need(nonempty(entry.get('quote'), 'reviewer quote') in draft['text'], 'Reviewer quote not found in current draft')
        nonempty(entry.get('reason'), 'reviewer evidence reason')
    issues = array(body.get('issues'), 'reviewer issues')
    need(body['verdict'] != 'pass' or not issues, 'A passing reviewer cannot leave unresolved issues')
    need(body['verdict'] != 'fail' or bool(issues), 'A failing reviewer must state the remaining issues')
    finding_errors = review_findings.validate(body, draft['text'])
    finding_errors.extend(review_findings.validate_development(body, draft['text'], role, baselines=baselines))
    if role == 'reader':
        finding_errors.extend(review_findings.validate_reading(body, draft['text']))
    need(not finding_errors, '; '.join(finding_errors))
    if role == 'professional':
        value_errors = context_value.validate(body.get('context_review'), draft['text'], 'literary')
        value_errors.extend(source_attribution.validate(body.get('source_attribution'), draft['text'], attribution_source, 'source', 'literary'))
        malformed = [e for e in value_errors if e != 'context_value unresolved content selection' and not e.startswith('source_attribution unresolved')]
        need(not malformed and (body['verdict'] == 'fail' or not value_errors), '; '.join(value_errors))
    else:
        value_errors = source_attribution.validate(body.get('attribution_replay'), draft['text'], profile='literary')
        malformed = [e for e in value_errors if not e.startswith('source_attribution unresolved')]
        need(not malformed and (body['verdict'] == 'fail' or not value_errors), '; '.join(value_errors))
    others = [r for r in state.get('reviewer_records', [])
              if r['draft_id'] == draft['id'] and r['body']['role'] != role]
    self_contexts = [r['body'].get('context_id') for r in state['reviews']]
    need(context not in self_contexts and all(r['body']['context_id'] != context for r in others),
         'Professional, reader and declared self-check contexts must be different')
    need(result_path, 'Native final reviewer result file is required')
    path = Path(result_path).resolve()
    need(read_json(path) == body, 'Reviewer result file differs from the submitted record')
    record = dict(draft_id=draft['id'], sha256=draft['sha256'], body=body,
                  result_path=str(path), result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    state.setdefault('reviewer_records', []).append(record)
    event(state, 'reviewer', str(path))
    return {'role': role, 'verdict': body['verdict'], 'draft_id': draft['id']}


def final_reviewers(state):
    draft = current(state)
    records = {}
    for record in state.get('reviewer_records', []):
        if record['draft_id'] == draft['id'] and record['sha256'] == draft['sha256']:
            records[record['body']['role']] = record
    return records


def reviewer_signature(state):
    return {role: record['result_sha256'] for role, record in final_reviewers(state).items()}


def editorial_binding(record):
    return dict(draft_id=record['draft_id'], artifact_sha256=record['sha256'],
                role=record['body']['role'], context_id=record['body']['context_id'],
                packet_sha256=record['body']['packet_sha256'],
                reviewer_receipt=dict(path=record['result_path'], sha256=record['result_sha256']))


def validate_editorial_decision(state, body):
    need(body.get('choice') in ('retain', 'revise', 'defer'), 'Editorial choice must be retain, revise or defer')
    nonempty(body.get('reason'), 'editorial decision reason')
    draft = current(state)
    evidence(state, body.get('evidence'), [draft['id']])
    need(all(e['artifact'] == draft['id'] for e in body['evidence']),
         'Editorial decision evidence must cite only the current draft')
    if body['choice'] == 'retain':
        record = final_reviewers(state).get(body.get('role'))
        finding = next((f for f in (record or {}).get('body', {}).get('editorial', [])
                        if f['id'] == body.get('finding_id')), None)
        trial_errors = review_findings.validate_trial(body.get('trial'), draft['text'],
                                                      finding['quote'] if finding else None)
        need(not trial_errors, '; '.join(trial_errors))


def editorial_review_state(state):
    """Return pending choices and latest receipt-bound decisions, never new verdicts."""
    draft = current(state)
    pending, decisions = [], []
    recorded = array(state.get('editorial_decisions', []), 'editorial_decisions')
    need(all(isinstance(d, dict) for d in recorded), 'Editorial decisions must be objects')
    for record in sorted(final_reviewers(state).values(), key=lambda r: r['body']['role']):
        errors = review_findings.validate(record['body'], draft['text'])
        need(not errors, '; '.join(errors))
        binding = editorial_binding(record)
        for finding in record['body'].get('editorial', []):
            key = dict(binding, finding_id=finding['id'])
            matches = [d for d in recorded
                       if all(d.get(k) == v for k, v in key.items())]
            decision = matches[-1] if matches else None
            if decision:
                validate_editorial_decision(state, decision)
                decisions.append(decision)
            if not decision or decision['choice'] != 'retain':
                pending.append(dict(key, impact=finding['impact'], reason=finding['reason'], quote=finding['quote']))
    pending, decisions = json.loads(json.dumps([pending, decisions]))
    return pending, decisions


def decide_editorial(state, body):
    """Record an author choice separately from the unchanged independent return."""
    body = json.loads(json.dumps(body))
    validate_storage(state)
    draft = current(state)
    need(body.get('draft_id') == draft['id'], 'Editorial decision is not for the current draft')
    need(digest(read_text(draft['origin'])) == draft['sha256'], 'Working draft changed; register a new version')
    role = body.get('role')
    need(role in ('professional', 'reader'), 'Editorial decision needs a reviewer role')
    record = final_reviewers(state).get(role)
    need(record is not None, 'No current reviewer receipt for this role')
    binding = editorial_binding(record)
    need(body.get('reviewer_receipt') == binding['reviewer_receipt'], 'Editorial decision reviewer receipt differs')
    need(all(k not in body or body[k] == v for k, v in binding.items()), 'Editorial decision binding differs')
    path = Path(record['result_path'])
    need(hashlib.sha256(path.read_bytes()).hexdigest() == record['result_sha256']
         and read_json(path) == record['body'], 'Native reviewer result changed')
    errors = review_findings.validate(record['body'], draft['text'])
    need(not errors, '; '.join(errors))
    identifier = nonempty(body.get('finding_id'), 'editorial finding_id')
    need(any(f['id'] == identifier for f in record['body'].get('editorial', [])),
         'Finding is not an editorial choice in this reviewer receipt')
    validate_editorial_decision(state, body)
    decision = dict(body, **binding, at=now())
    state.setdefault('editorial_decisions', []).append(decision)
    event(state, 'editorial-decide', len(state['editorial_decisions']))
    return dict(status='editorial-choice-recorded', role=role, draft_id=draft['id'],
                finding_id=identifier, choice=body['choice'], resolved=body['choice'] == 'retain')


def native_review_payload(state):
    validate_storage(state)
    draft = current(state)
    reviewers = final_reviewers(state)
    need(set(reviewers) == {'professional', 'reader'}, 'Both fresh reviewer roles are required')
    for record in reviewers.values():
        need(hashlib.sha256(Path(record['result_path']).read_bytes()).hexdigest() == record['result_sha256']
             and read_json(record['result_path']) == record['body'],
             'Native reviewer result changed')
    need({'clean', 'comparison'} <= set(latest_reviews(state)), 'Complete clean/comparison self-checks first')
    issues = [{'impact': reason} for reason in blockers(state, require_decision=False)]
    issues += [issue for record in reviewers.values() for issue in record['body']['issues']]
    issues += [{'impact': error} for error in source_attribution.compare(reviewers['professional']['body'].get('source_attribution'),
                                                                    reviewers['reader']['body'].get('attribution_replay'))]
    pending, editorial_decisions = editorial_review_state(state)
    issues += [dict(finding, kind='pending_editorial_choice') for finding in pending]
    passed = all(record['body']['verdict'] == 'pass' for record in reviewers.values()) and not issues
    result = dict(status='pass' if passed else 'fail', draft_id=draft['id'], artifact_sha256=draft['sha256'],
                  reviewer_records=[reviewers[role]['body'] for role in ('professional', 'reader')], issues=issues,
                  self_review_ids={phase: review['id'] for phase, review in latest_reviews(state).items()})
    if pending or editorial_decisions:
        result.update(pending_editorial=pending, editorial_decisions=editorial_decisions)
    return json.loads(json.dumps(result))


def bind_review_result(state, result_path):
    expected = native_review_payload(state)
    path = Path(result_path)
    raw = read_json(path)
    records = array(raw.get('reviewer_records'), 'native final reviewer_records')
    need(len(records) == 2 and all(isinstance(r, dict) for r in records), 'Require two native reviewer records')
    need(all('draft_id' not in r or r['draft_id'] == expected['draft_id'] for r in records),
         'Native aggregate reviewer belongs to an older draft')
    strip_version = lambda r: {k: v for k, v in r.items() if k != 'draft_id'}
    need(sorted((strip_version(r) for r in records), key=lambda r: r['role']) ==
         sorted((strip_version(r) for r in expected['reviewer_records']), key=lambda r: r['role']),
         'Aggregate differs from the native final reviewer records')
    for field in ('status', 'draft_id', 'artifact_sha256', 'self_review_ids'):
        need(field not in raw or raw[field] == expected[field], 'Native result disagrees with current ' + field)
    need('verdict' not in raw or raw['verdict'] == expected['status'], 'Native aggregate verdict disagrees with reviewers')
    canonical_issues = lambda entries: {json.dumps(issue, sort_keys=True, ensure_ascii=False) for issue in entries}
    need(canonical_issues(array(raw.get('issues'), 'native issues')) == canonical_issues(expected['issues']),
         'Native result omits or changes unresolved findings')
    for field in ('pending_editorial', 'editorial_decisions'):
        need(raw.get(field, []) == expected.get(field, []), 'Native result omits or changes ' + field)
    draft = current(state)
    state.setdefault('review_results', []).append(dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                 draft_id=draft['id'], artifact_sha256=draft['sha256'], reviewers=reviewer_signature(state),
                 self_review_ids=expected['self_review_ids'], editorial_decisions=expected.get('editorial_decisions', [])))
    event(state, 'review-result', str(path.resolve()))
    return dict(status=expected['status'], result_path=str(path.resolve()))


def write_review_result(state, destination):
    """Produce the native result consumed by lifecycle.finish_review."""
    result = native_review_payload(state)
    path = Path(destination)
    need(not path.exists() and not path.is_symlink(), 'Native result target exists; use a new round path')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    path.chmod(0o600)
    return bind_review_result(state, path)


def check(state, final=None, *, lifecycle_run=None, draft=False):
    validate_storage(state)
    result = check_records(state, final)
    reasons = result['blockers']
    item = current(state)
    reviewers = final_reviewers(state)
    editorial_decisions = []
    try:
        pending, editorial_decisions = editorial_review_state(state)
        result.update(pending_editorial=pending, editorial_decisions=editorial_decisions)
        reasons.extend('pending_editorial_choice:' + f['role'] + '/' + f['finding_id'] for f in pending)
    except (ValueError, KeyError, TypeError) as error:
        reasons.append('editorial_findings_invalid:' + str(error))
    paths = []
    for role in ('professional', 'reader'):
        record = reviewers.get(role)
        if not record:
            reasons.append('missing_fresh_' + role + '_review_for_current_draft')
            continue
        path = Path(record['result_path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record['result_sha256']:
            reasons.append('reviewer_result_changed:' + role)
        if not draft and record['body']['verdict'] != 'pass':
            reasons.append('reviewer_not_passed:' + role)
        paths.append(str(path))
    results = state.get('review_results', [])
    native = results[-1] if results else None
    if not native or native['draft_id'] != item['id'] or native['artifact_sha256'] != item['sha256']:
        reasons.append('missing_native_review_result_for_current_draft')
    elif native['reviewers'] != reviewer_signature(state) or native['self_review_ids'] != {
            phase: review['id'] for phase, review in latest_reviews(state).items()} or native.get('editorial_decisions', []) != editorial_decisions:
        reasons.append('native_review_result_predates_latest_review')
    elif not Path(native['path']).is_file() or hashlib.sha256(Path(native['path']).read_bytes()).hexdigest() != native['sha256']:
        reasons.append('native_review_result_changed')
    else:
        paths.append(native['path'])
    try:
        linked = lifecycle_location(state, lifecycle_run)
        need(item.get('lifecycle_run') == linked and item.get('checkpoint'),
             'Current draft lacks lifecycle preparation/unit checkpoint association')
        lifecycle_registration(state, linked, item['origin'], item['checkpoint'])
        lifecycle = importlib.import_module('writing_lifecycle')
        verified = lifecycle.verify_delivery(linked, item['origin'], 'literary',
                                             review_evidence=paths, draft=draft)
        need(verified.get('artifact_sha256') == item['sha256'], 'Lifecycle verified a stale artifact version')
        need(verified.get('status') in ('pass', 'review-incomplete-draft'), 'Unexpected lifecycle verification status')
        need(draft or verified['status'] == 'pass', 'Incomplete draft cannot be delivered as complete')
        result['lifecycle'] = verified
        result['boundary'] = ('Verifies native self-checks, final reviewer evidence and registered lifecycle stages; '
                              'not reviewer identity, literary quality, generation order, or publication permission.')
        if verified['status'] == 'review-incomplete-draft':
            # Failed semantic findings remain visible; missing/stale records never become draft permission.
            soft = ('unresolved_issue:', 'unsupported_character_change', 'comparison_not_decided', 'pending_editorial_choice:')
            decisions = [d for d in state['decisions'] if d['draft_id'] == item['id']]
            if decisions and decisions[-1]['choice'] in ('retry', 'defer') and decisions[-1]['review_ids'] == {
                    phase: review['id'] for phase, review in latest_reviews(state).items()}:
                soft += ('missing_final_choice',)
            result['remaining_issues'] = list(reasons)
            reasons[:] = [reason for reason in reasons if not reason.startswith(soft)]
            result['notice'] = ('Three review rounds completed; the current version still has a failing review and unresolved issues. '
                                'Draft only, not independently passed or approved for publication.')
            result['next_question'] = 'Which unresolved issue or writing direction should be addressed next? No fourth round was started.'
    except (ImportError, OSError, ValueError, KeyError, TypeError) as error:
        reasons.append('lifecycle_blocked:' + str(error))
    result['status'] = 'blocked' if reasons else result['lifecycle']['status']
    if not reasons:
        try:
            import writing_execution
            result['managed_execution'] = writing_execution.accept_native(
                linked, item['origin'], [native['path']],
                {'status': result['status'], 'artifact_sha256': item['sha256']})
        except (OSError, ValueError, KeyError, TypeError) as error:
            reasons.append('execution_blocked:' + str(error))
            result['status'] = 'blocked'
    return result


def deliver(state, destination, *, lifecycle_run=None, draft=False):
    result = check(state, lifecycle_run=lifecycle_run, draft=draft)
    need(not result['blockers'], '; '.join(result['blockers']))
    path = Path(destination)
    need(not path.exists() and not path.is_symlink(), 'Delivery target exists; no automatic overwrite')
    notice = Path(str(path) + '.notice.json') if result['status'] == 'review-incomplete-draft' else None
    if notice:
        need(not notice.exists() and not notice.is_symlink(), 'Draft notice target exists; no automatic overwrite')
    data = current(state)['text'].encode('utf-8')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
    need(hashlib.sha256(path.read_bytes()).hexdigest() == result['sha256'], 'Delivery verification failed')
    if notice:
        try:
            with notice.open('x', encoding='utf-8') as handle:
                json.dump(result, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
        except Exception:
            path.unlink()
            raise
        result['notice_path'] = str(notice.resolve())
    event(state, 'deliver', str(path.resolve()))
    return dict(result, delivery=str(path.resolve()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('run')
    init.add_argument('--contract', required=True)
    init.add_argument('--source')
    for command in ('prepare', 'draft', 'review', 'review-result', 'decide', 'editorial-decide', 'check', 'deliver', 'inspect'):
        child = commands.add_parser(command)
        child.add_argument('run')
        if command == 'prepare':
            child.add_argument('--lifecycle-run', required=True)
            child.add_argument('--record')
            child.add_argument('--reason', required=True)
            child.add_argument('--timing', choices=['prewrite', 'during', 'retrospective'], default='prewrite')
        elif command == 'draft':
            child.add_argument('--lifecycle-run', required=True)
            child.add_argument('--checkpoint', required=True)
            child.add_argument('--id', required=True)
            child.add_argument('--file', required=True)
        elif command in ('review', 'decide', 'editorial-decide'):
            child.add_argument('--file', required=True)
        elif command == 'review-result':
            target = child.add_mutually_exclusive_group(required=True)
            target.add_argument('--to')
            target.add_argument('--file')
        elif command == 'check':
            child.add_argument('--lifecycle-run', required=True)
            child.add_argument('--draft', action='store_true', dest='incomplete_draft')
            child.add_argument('--final')
        elif command == 'deliver':
            child.add_argument('--lifecycle-run', required=True)
            child.add_argument('--draft', action='store_true', dest='incomplete_draft')
            child.add_argument('--to', required=True)
        elif command == 'inspect':
            child.add_argument('--artifact')
            child.add_argument('--diff', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            result = init_run(args.run, read_json(args.contract), args.source)
        else:
            with session(args.run, write=args.command not in ('check', 'inspect')) as state:
                if args.command == 'prepare':
                    result = prepare(state, args.record, args.reason, args.timing, lifecycle_run=args.lifecycle_run)
                elif args.command == 'draft':
                    result = add_draft(state, args.id, args.file, lifecycle_run=args.lifecycle_run, checkpoint=args.checkpoint)
                elif args.command == 'review':
                    body = read_json(args.file)
                    result = add_reviewer_record(state, body, args.file) if 'role' in body else add_review(state, body)
                elif args.command == 'decide':
                    result = decide(state, read_json(args.file))
                elif args.command == 'editorial-decide':
                    result = decide_editorial(state, read_json(args.file))
                elif args.command == 'review-result':
                    result = write_review_result(state, args.to) if args.to else bind_review_result(state, args.file)
                elif args.command == 'check':
                    result = check(state, args.final, lifecycle_run=args.lifecycle_run, draft=args.incomplete_draft)
                elif args.command == 'deliver':
                    result = deliver(state, args.to, lifecycle_run=args.lifecycle_run, draft=args.incomplete_draft)
                elif args.artifact:
                    need(args.artifact in objects(state), 'Unknown artifact id')
                    print(objects(state)[args.artifact]['text'])
                    return 0
                elif args.diff:
                    need(state['source'] is not None, 'No source for comparison')
                    print(''.join(difflib.unified_diff(state['source']['text'].splitlines(True),
                              current(state)['text'].splitlines(True), fromfile='source', tofile=current(state)['id'])))
                    return 0
                else:
                    result = {'contract': state['contract'], 'artifacts': list(objects(state)),
                              'events': state['events'], 'issues': issue_index(state)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if isinstance(result, dict) and result.get('status') == 'blocked' else 0
    except (ImportError, OSError, ValueError, UnicodeError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'error', 'message': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
