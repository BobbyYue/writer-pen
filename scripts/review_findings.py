"""Literary review records check actual responses and trials, not artistic merit."""
import re

GUIDANCE = (
    'Return verdict (pass/fail), summary, evidence [{quote,reason}], and issues '
    '[{impact,reason}]. issues contains blocking findings, including legacy issues: '
    'verdict must be fail if and only if issues is nonempty. Never move a constraint, '
    'unsupported claim or coherence blocker into a softer category to obtain pass. '
    'Optionally return editorial and suggestions, each a list of '
    '{id,impact,reason,quote}. Use unique nonempty IDs across these two lists and '
    'exact quotes from the current draft, not source text or a paraphrase. '
    'editorial requests an author choice between supported artistic alternatives; '
    'it does not by itself make the reviewer verdict fail. An unresolved editorial '
    'choice still prevents final completion until the author explicitly retains it '
    'with reason and current-draft evidence, or revises and obtains new reviews. '
    'suggestions are optional improvements and never block completion. '
    'Do not manufacture findings or author approvals. Omitted new lists mean no '
    'findings in those categories. Transport identity and draft bindings are supplied '
    'by the caller; return the role-specific evidence templates as requested. '
    'Professionals must return development_response: a nonempty observation, an '
    'exact current-draft quote, disposition (supported/blocker/editorial/not-applicable), '
    'and finding_ids, plus a required checks object containing every ID in the supplied '
    'review-coverage methods, with no omitted or additional IDs. Each check contains before_quote, after_quote, '
    'observation, disposition and finding_ids. Both quotes must be nonempty exact '
    'passages from the current body, not an earlier draft or source material. '
    'scene_continuity must examine relevant cross-paragraph scene transitions: '
    'whether orientation, participants, objects and available knowledge connect '
    'where relevant. motivation_action must examine whether triggers, character '
    'responses, actions and consequences connect in this text. Explain the actual '
    'relationship or uncertainty in observation; a generic claim that it works '
    'is not a review. Do not require explicit time and place in every scene, '
    'chronological narration, an action in every paragraph or omniscient access '
    'to motives. Explain unknowns and not-applicable judgments from the actual '
    'text rather than inventing missing premises. '
    'Supported and not-applicable must leave finding_ids empty. Blocker must link '
    'to stable unique IDs in issues and verdict must be fail; editorial must link '
    'to IDs in editorial. Do not reuse linked IDs across finding categories. '
    'Each check also returns comparison {needed:boolean, reason:nonempty text, trial:object|null}. '
    'When needed is true and disposition is supported, supply a real trial with current, '
    'alternative, gain, loss and attention_cost. trial.current must include a checked '
    'quote and the actual edit context. For paragraph_rhythm it must include BOTH '
    'boundary quotes so the merge/split is actually compared. Other local trials '
    'need not copy all intervening text; use the paired quotes and observation '
    'to explain the related consequence. '
    'For pure paragraph changes use kind:paragraphing. When needed is true but comparison '
    'is still pending, use a linked editorial or blocker rather than supported. A negative '
    'or editorial finding may remain for the existing author resolution, not a new round. '
    'When no comparison is needed, explain why for this text and leave trial null. '
    'revision_effects also returns baseline_evidence [{id,sha256,quote,reason}]. '
    'Use exact supplied source:1 and candidate:previous evidence when available; '
    'cover both when both exist. Do not cite the current draft as its own baseline '
    'or invent an earlier version. Without supplied baselines, use an empty list. '
    'These same binding rules apply to every check in the same return. Any child '
    'blocker requires verdict fail and parent disposition blocker; a child '
    'editorial requires parent disposition editorial or blocker. A supported or '
    'not-applicable parent cannot hide unresolved child findings. '
    'Not-applicable applies only to an absent relationship, not a blanket prose exemption. '
    'language_detail, paragraph_rhythm and title_opening_ending always need a judgment; '
    'revision_effects cannot be exempted when a baseline is supplied. For absent plot relationships: '
    'still quote the body and explain why in each observation; a not-applicable '
    'check may use the same short passage for both quotes. Do not require conflict, '
    'a scene count, objective rationality or literal adherence to source wording. '
    'These records and bindings do not establish literary quality. This response '
    'belongs only to professional review; readers receive no source materials or '
    'author choices and must not return development_response. '
    'Readers must return reading_response: understanding and experience each '
    'contain observation and an exact quote. Experience also contains disposition '
    '(no-change/editorial/suggestion) and finding_ids referencing the matching '
    'editorial or suggestions entries. Understanding does not prove engagement. '
    'An unengaged or uncertain response is valid; never invent praise, symbolism, '
    'human timing or feelings. No-change is a supported editorial judgment, not '
    'a requirement to enjoy the work. Report a consequential unresolved artistic '
    'choice as editorial, not only a generic positive summary.'
)

_TEXT = {'type': 'string', 'minLength': 1}
_FINDING = {'type': 'object', 'required': ['id', 'impact', 'reason', 'quote'],
            'properties': {name: _TEXT for name in ('id', 'impact', 'reason', 'quote')}}
_RESPONSE = {'type': 'object', 'required': ['understanding', 'experience'], 'properties': {
    'understanding': {'type': 'object', 'required': ['observation', 'quote'],
                      'properties': {'observation': _TEXT, 'quote': _TEXT}},
    'experience': {'type': 'object', 'required': ['observation', 'quote', 'disposition', 'finding_ids'],
                   'properties': {'observation': _TEXT, 'quote': _TEXT,
                       'disposition': {'enum': ['no-change', 'editorial', 'suggestion']},
                       'finding_ids': {'type': 'array', 'items': _TEXT}}}}}
import literary_methods

_DEVELOPMENT_CHECK_NAMES = literary_methods.check_names()
_DEVELOPMENT_DISPOSITION = {'enum': ['supported', 'blocker', 'editorial', 'not-applicable']}
_DEVELOPMENT_CHECK = {'type': 'object',
                      'required': ['before_quote', 'after_quote', 'observation', 'disposition', 'finding_ids', 'comparison'],
                      'properties': {'before_quote': _TEXT, 'after_quote': _TEXT, 'observation': _TEXT,
                          'disposition': _DEVELOPMENT_DISPOSITION,
                          'finding_ids': {'type': 'array', 'items': _TEXT},
                          'comparison': {'type': 'object', 'required': ['needed', 'reason', 'trial'],
                              'properties': {'needed': {'type': 'boolean'}, 'reason': _TEXT,
                                  'trial': {'anyOf': [{'type': 'null'}, {'type': 'object',
                                      'required': ['current', 'alternative', 'gain', 'loss', 'attention_cost'],
                                      'properties': {key: _TEXT for key in ('current', 'alternative', 'gain', 'loss', 'attention_cost')}}]}}}}}
def _check_schema(name):
    import copy
    result = copy.deepcopy(_DEVELOPMENT_CHECK)
    if name == 'revision_effects':
        result['required'].append('baseline_evidence')
        result['properties']['baseline_evidence'] = {'type': 'array', 'items': {'type': 'object',
            'required': ['id', 'sha256', 'quote', 'reason'],
            'properties': {key: _TEXT for key in ('id', 'sha256', 'quote', 'reason')}}}
    return result


_DEVELOPMENT = {'type': 'object', 'required': ['observation', 'quote', 'disposition', 'finding_ids', 'checks'],
                'properties': {'observation': _TEXT, 'quote': _TEXT,
                    'disposition': _DEVELOPMENT_DISPOSITION,
                    'finding_ids': {'type': 'array', 'items': _TEXT},
                    'checks': {'type': 'object', 'required': list(_DEVELOPMENT_CHECK_NAMES),
                               'additionalProperties': False,
                               'properties': {name: _check_schema(name) for name in _DEVELOPMENT_CHECK_NAMES}}}}
RESULT_SCHEMA = {
    'type': 'object', 'required': ['verdict', 'summary', 'evidence', 'issues'],
    'properties': {
        'verdict': {'enum': ['pass', 'fail']}, 'summary': _TEXT,
        'evidence': {'type': 'array', 'minItems': 1, 'items': {
            'type': 'object', 'required': ['quote', 'reason'],
            'properties': {'quote': _TEXT, 'reason': _TEXT}}},
        'issues': {'type': 'array', 'items': {'type': 'object', 'required': ['impact'],
                   'properties': {'impact': _TEXT, 'reason': _TEXT}}},
        'editorial': {'type': 'array', 'items': _FINDING},
        'suggestions': {'type': 'array', 'items': _FINDING},
        'reading_response': _RESPONSE,
        'development_response': _DEVELOPMENT,
    },
}


def result_schema(role, *, compact=False):
    import copy
    result = copy.deepcopy(RESULT_SCHEMA)
    checks = result['properties']['development_response']['properties']['checks']
    names = literary_methods.check_names()
    checks['required'] = list(names)
    checks['properties'] = {name: _check_schema(name) for name in names}
    if role == 'reader':
        result['required'].append('reading_response')
        result['properties'].pop('development_response')
        import source_attribution
        result['required'].append('attribution_replay')
        result['properties']['attribution_replay'] = source_attribution.result_schema()
    elif role == 'professional':
        result['required'].append('development_response')
        result['properties'].pop('reading_response')
        import source_attribution
        import context_value
        result['required'].extend(['source_attribution', 'context_review'])
        result['properties']['source_attribution'] = source_attribution.result_schema()
        result['properties']['context_review'] = context_value.result_schema()
        if compact:
            result['$defs'] = {'literary_check': _check_schema('scene_continuity'),
                               'literary_revision_check': _check_schema('revision_effects')}
            checks['properties'] = {name: {'$ref': '#/$defs/' + (
                'literary_revision_check' if name == 'revision_effects' else 'literary_check')} for name in names}
    return result


def validate_basis(value):
    """Separate givens, provisional readings and choices; do not judge their truth."""
    if not isinstance(value, dict):
        return ['writing_basis must separate given, interpretations and choices']
    errors = []
    for key in ('given', 'interpretations', 'choices'):
        entries = value.get(key)
        if not isinstance(entries, list) or any(not isinstance(e, str) or not e.strip() for e in entries):
            errors.append('writing_basis.' + key + ' must be a list of nonempty text')
    if isinstance(value.get('choices'), list) and not value['choices']:
        errors.append('writing_basis.choices must record the current adjustable choice')
    return errors


def validate_working_title(value):
    if not isinstance(value, dict) or not isinstance(value.get('reason'), str) or not value['reason'].strip():
        return ['Record working_title with text and reason before drafting; explicit untitled uses text:null']
    if 'text' not in value or not (value['text'] is None or isinstance(value['text'], str) and value['text'].strip()):
        return ['working_title.text must be nonempty text or null for an explicit untitled request']
    return []


def reading_template():
    return {'understanding': {'observation': '', 'quote': ''},
            'experience': {'observation': '', 'quote': '', 'disposition': '', 'finding_ids': []}}


def development_template():
    result = {'observation': '', 'quote': '', 'disposition': '', 'finding_ids': [],
            'checks': {name: {'before_quote': '', 'after_quote': '', 'observation': '',
                              'disposition': '', 'finding_ids': [],
                              'comparison': {'needed': False, 'reason': '', 'trial': None}}
                       for name in literary_methods.check_names()}}
    result['checks']['revision_effects']['baseline_evidence'] = []
    return result


def baselines_from_packet(packet):
    result = []
    if packet.get('sources'):
        result.append(dict(packet['sources'][0], id='source:1'))
    if packet.get('comparison_baseline'):
        result.append(packet['comparison_baseline'])
    return result


def _validate_development_item(body, value, text, label, quote_fields):
    """Use the same anchor and finding rules for the overall record and checks."""
    if not isinstance(value, dict):
        return [label + ' must include observation, ' + ', '.join(quote_fields) + ', disposition and finding_ids']
    errors = []
    for name in ('observation',) + quote_fields:
        if not isinstance(value.get(name), str) or not value[name].strip():
            errors.append(label + '.' + name + ' must be nonempty text')
    for name in quote_fields:
        if text is not None and isinstance(value.get(name), str) and value[name] not in text:
            errors.append(label + '.' + name + ' is not in the current draft')
    action, ids = value.get('disposition'), value.get('finding_ids')
    if action not in ('supported', 'blocker', 'editorial', 'not-applicable'):
        errors.append(label + ' disposition is invalid')
    if not isinstance(ids, list) or any(not isinstance(i, str) or not i.strip() for i in ids):
        errors.append(label + ' finding_ids must be a list of text')
        return errors
    if len(ids) != len(set(ids)):
        errors.append(label + ' finding_ids are duplicated')
    if action in ('supported', 'not-applicable') and ids:
        errors.append(label + ' ' + action + ' cannot leave finding_ids')
    if action == 'blocker' and body.get('verdict') != 'fail':
        errors.append(label + ' blocker requires verdict fail')
    if action in ('blocker', 'editorial'):
        field = 'issues' if action == 'blocker' else 'editorial'
        entries = body.get(field, [])
        available = [e['id'] for e in entries if isinstance(e, dict) and isinstance(e.get('id'), str)] if isinstance(entries, list) else []
        if not ids or any(available.count(i) != 1 for i in ids):
            errors.append(label + ' needs its matching ' + field + ' findings with stable unique IDs')
        for other in ('issues', 'editorial', 'suggestions'):
            if other == field:
                continue
            entries = body.get(other, [])
            if isinstance(entries, list) and any(isinstance(e, dict) and e.get('id') in ids for e in entries):
                errors.append(label + ' finding_ids are ambiguous across ' + field + ' and ' + other)
    return errors


def validate_development(body, text=None, role='professional', baselines=None):
    """Check review coverage, anchors and links, not whether development works."""
    if role != 'professional':
        return ['development_response is only valid for professional reviewers'] if 'development_response' in body else []
    if body.get('role', role) != role:
        return ['development_response belongs to the professional reviewer role']
    value = body.get('development_response')
    errors = _validate_development_item(body, value, text, 'development_response', ('quote',))
    if not isinstance(value, dict):
        return errors
    checks = value.get('checks')
    names = literary_methods.check_names()
    if not isinstance(checks, dict):
        return errors + ['development_response.checks must include all registered checks: ' + ', '.join(names)]
    if set(checks) != set(names):
        errors.append('development_response.checks must contain exactly: ' + ', '.join(names))
    for name in names:
        item = checks.get(name)
        label = 'development_response.checks.' + name
        errors.extend(_validate_development_item(body, item, text, label, ('before_quote', 'after_quote')))
        if not isinstance(item, dict):
            continue
        comparison = item.get('comparison')
        if not isinstance(comparison, dict) or type(comparison.get('needed')) is not bool:
            errors.append(label + '.comparison needs an explicit needed boolean')
        elif not isinstance(comparison.get('reason'), str) or not comparison['reason'].strip() or 'trial' not in comparison:
            errors.append(label + '.comparison needs a concrete reason and trial or null')
        elif comparison['needed'] and item.get('disposition') == 'not-applicable':
            errors.append(label + '.comparison cannot be needed for a not-applicable check')
        elif comparison['needed'] and item.get('disposition') == 'supported':
            trial = comparison.get('trial')
            trial_text = text if text is not None else trial.get('current', '') if isinstance(trial, dict) else ''
            anchors = [item.get(k) for k in ('before_quote', 'after_quote') if isinstance(item.get(k), str)]
            current_trial = trial.get('current', '') if isinstance(trial, dict) else ''
            matching = [q for q in anchors if isinstance(current_trial, str) and q in current_trial]
            errors.extend(label + ': ' + error for error in validate_trial(trial, trial_text, matching[0] if matching else None))
            if not matching:
                errors.append(label + ': trial.current must cover a checked passage')
            if name == 'paragraph_rhythm' and isinstance(current_trial, str) and any(q not in current_trial for q in anchors):
                errors.append(label + ': trial.current must cover both inspected quotes')
        elif not comparison['needed'] and comparison['trial'] is not None:
            errors.append(label + '.comparison cannot provide a trial while saying it was not needed')
        elif comparison.get('trial') is not None:
            trial = comparison['trial']
            trial_text = text if text is not None else trial.get('current', '') if isinstance(trial, dict) else ''
            before = item.get('before_quote') if isinstance(item.get('before_quote'), str) else None
            errors.extend(label + ': ' + error for error in validate_trial(trial, trial_text, before))
        if name in ('language_detail', 'paragraph_rhythm', 'title_opening_ending') and item.get('disposition') == 'not-applicable':
            errors.append(label + ' still requires review for prose, a single paragraph or an untitled work')
        if name == 'revision_effects':
            evidence = item.get('baseline_evidence')
            if not isinstance(evidence, list):
                errors.append(label + '.baseline_evidence must be an explicit list')
            else:
                seen = set()
                available = {b['id']: b for b in baselines or []}
                for anchor in evidence:
                    if not isinstance(anchor, dict) or any(not isinstance(anchor.get(k), str) or not anchor[k].strip()
                                                          for k in ('id', 'sha256', 'quote', 'reason')):
                        errors.append(label + '.baseline_evidence has incomplete fields')
                        continue
                    if anchor['id'] in seen or not re.fullmatch('[a-f0-9]{64}', anchor['sha256']):
                        errors.append(label + '.baseline_evidence needs unique IDs and exact hashes')
                    seen.add(anchor['id'])
                    baseline = available.get(anchor['id'])
                    if baselines is not None and not baseline:
                        errors.append(label + '.baseline_evidence refers to an unregistered baseline')
                    if baseline and (baseline['sha256'] != anchor['sha256'] or anchor['quote'] not in baseline['text']):
                        errors.append(label + '.baseline_evidence does not match the registered baseline')
                if baselines is not None:
                    if not set(available) <= seen:
                        errors.append(label + '.baseline_evidence must cover each registered baseline')
                    if not available and evidence:
                        errors.append(label + '.baseline_evidence cannot invent an earlier version')
                    if available and item.get('disposition') == 'not-applicable':
                        errors.append(label + ' cannot exempt a supplied comparison baseline')
        if name == 'paragraph_rhythm' and text is not None and re.search(r'\n[ \t]*\n', text):
            quotes = [item.get(key) for key in ('before_quote', 'after_quote')]
            if all(isinstance(q, str) and q for q in quotes):
                boundary = any(re.search(r'\n[ \t]*\n', q) for q in quotes)
                if not boundary:
                    for before in re.finditer(re.escape(quotes[0]), text):
                        for after in re.finditer(re.escape(quotes[1]), text):
                            gap = text[before.end():after.start()] if after.start() >= before.end() else ''
                            if len(re.findall(r'\n[ \t]*\n', gap)) == 1:
                                boundary = True
                if not boundary:
                    errors.append(label + ' must inspect an actual paragraph boundary, not only one paragraph interior')
        if item.get('disposition') == 'blocker' and value.get('disposition') != 'blocker':
            errors.append('development_response disposition must be blocker when ' + label + ' is blocker')
        if item.get('disposition') == 'editorial' and value.get('disposition') not in ('editorial', 'blocker'):
            errors.append('development_response disposition must be editorial or blocker when ' + label + ' is editorial')
    return errors


def validate_reading(body, text=None):
    value = body.get('reading_response')
    if not isinstance(value, dict):
        return ['reading_response must include understanding and experience']
    errors = []
    for key in ('understanding', 'experience'):
        item = value.get(key)
        if not isinstance(item, dict):
            errors.append('reading_response.' + key + ' is missing')
            continue
        for name in ('observation', 'quote'):
            if not isinstance(item.get(name), str) or not item[name].strip():
                errors.append('reading_response.' + key + '.' + name + ' must be nonempty text')
        if text is not None and isinstance(item.get('quote'), str) and item['quote'] not in text:
            errors.append('reading_response.' + key + '.quote is not in the current draft')
    experience = value.get('experience')
    if not isinstance(experience, dict):
        return errors
    action = experience.get('disposition')
    ids = experience.get('finding_ids')
    if action not in ('no-change', 'editorial', 'suggestion'):
        errors.append('reading_response.experience disposition is invalid')
    if not isinstance(ids, list) or any(not isinstance(i, str) or not i.strip() for i in ids):
        errors.append('reading_response.experience finding_ids must be a list of text')
        return errors
    if len(ids) != len(set(ids)):
        errors.append('reading_response.experience finding_ids are duplicated')
    if action == 'no-change' and ids:
        errors.append('no-change experience cannot leave finding_ids')
    if action in ('editorial', 'suggestion'):
        entries = body.get('editorial' if action == 'editorial' else 'suggestions', [])
        available = {e['id'] for e in entries if isinstance(e, dict) and isinstance(e.get('id'), str)} if isinstance(entries, list) else set()
        if not ids or any(i not in available for i in ids):
            errors.append('reading_response experience needs its matching ' + action + ' findings')
    return errors


def validate_trial(value, text, quote=None):
    """Require a real alternative and its costs, never an automatic aesthetic pass."""
    if not isinstance(value, dict):
        return ['trial must include actual current and alternative passages']
    errors = []
    for name in ('current', 'alternative', 'gain', 'loss', 'attention_cost'):
        if not isinstance(value.get(name), str) or not value[name].strip():
            errors.append('trial.' + name + ' must be nonempty text')
    current, alternative = value.get('current'), value.get('alternative')
    if isinstance(current, str) and current.strip():
        if current not in text:
            errors.append('trial.current is not an exact current-draft passage')
        if quote and quote not in current:
            errors.append('trial.current must cover the finding quote and its needed context')
    kind = value.get('kind', 'content')
    if kind not in ('content', 'paragraphing'):
        errors.append('trial.kind must be content or paragraphing')
    if isinstance(current, str) and isinstance(alternative, str) and ''.join(current.split()) == ''.join(alternative.split()):
        def lines(value):
            return '\n'.join(' '.join(line.split()) for line in value.replace('\r\n', '\n').strip().split('\n'))
        if kind != 'paragraphing' or lines(current) == lines(alternative):
            errors.append('trial alternative is unchanged or has only incidental whitespace changes')
    return errors


def validate(body, text=None):
    """Validate only present new fields; optionally verify exact draft anchors.

    Legacy verdict/issues validation remains with the existing native validators.
    Missing optional lists are not filled in or written back to the raw review.
    """
    errors, identifiers = [], set()
    issues = body.get('issues', [])
    if not isinstance(issues, list):
        errors.append('issues must be a list of blocking findings')
    else:
        for item in issues:
            if not isinstance(item, dict) or not isinstance(item.get('impact'), str) or not item['impact'].strip():
                errors.append('issues require objects with a nonempty impact')
            elif 'reason' in item and (not isinstance(item['reason'], str) or not item['reason'].strip()):
                errors.append('issues reason must be nonempty when supplied')
    for field in ('editorial', 'suggestions'):
        if field not in body:
            continue
        entries = body[field]
        if not isinstance(entries, list):
            errors.append(field + ' must be a list')
            continue
        for index, entry in enumerate(entries):
            label = field + '[' + str(index) + ']'
            if not isinstance(entry, dict):
                errors.append(label + ' must be an object')
                continue
            for name in ('id', 'impact', 'reason', 'quote'):
                if not isinstance(entry.get(name), str) or not entry[name].strip():
                    errors.append(label + '.' + name + ' must be nonempty text')
            identifier = entry.get('id')
            if isinstance(identifier, str) and identifier.strip():
                if identifier in identifiers:
                    errors.append(label + ' duplicates finding id ' + identifier)
                identifiers.add(identifier)
            quote = entry.get('quote')
            if text is not None and isinstance(quote, str) and quote.strip() and quote not in text:
                errors.append(label + '.quote is not an exact current draft quote')
    return errors
