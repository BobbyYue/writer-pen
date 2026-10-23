"""Synthetic record builder for schema tests only; never a semantic verdict."""
import context_value
import source_attribution
import literary_methods


def structural_basis():
    return {'given': [], 'interpretations': [], 'choices': ['Synthetic adjustable choice, not a literary prescription']}


def structural_reading(text):
    return {'understanding': {'observation': 'STRUCTURAL FIXTURE understanding, not actual reading', 'quote': text},
            'experience': {'observation': 'STRUCTURAL FIXTURE experience, not human engagement', 'quote': text,
                           'disposition': 'no-change', 'finding_ids': []}}


def structural_development(text, baselines=None):
    result = {'observation': 'Synthetic development record: the quoted passage anchors the action and response in this fixture, not a literary verdict.',
            'quote': text, 'disposition': 'supported', 'finding_ids': [],
            'checks': {name: {'before_quote': text, 'after_quote': text,
                              'observation': 'STRUCTURAL FIXTURE ' + name + ', not a semantic review of continuity or motives.',
                              'disposition': 'supported', 'finding_ids': [],
                              'comparison': {'needed': False, 'reason': 'Synthetic fixture only; no literary comparison claimed.', 'trial': None}}
                       for name in literary_methods.check_names()}}
    result['checks']['revision_effects']['baseline_evidence'] = [
        {key: b[key] for key in ('id', 'sha256')} | dict(quote=b['text'], reason='Synthetic baseline binding only')
        for b in baselines or []]
    return result


def structural_trial(text):
    return {'current': text, 'alternative': text + ' Synthetic alternative passage.',
            'gain': 'STRUCTURAL FIXTURE gain', 'loss': 'STRUCTURAL FIXTURE loss',
            'attention_cost': 'STRUCTURAL FIXTURE attention cost, not a literary judgment'}


def structural_attribution(text, source='', mode='reader', profile='functional'):
    result = source_attribution.template(text, source, mode, profile)
    result['whole_text_scan'] = 'STRUCTURAL FIXTURE; not source or reader validation'
    for item in result['items']:
        item.update(kind='unknown', speaker='unknown', speaker_basis='', support_quote='', source_scope='unresolved',
                    negative_status='unconfirmed', basis='STRUCTURAL FIXTURE, not a semantic judgment', status='pass')
    return result


def structural_context(text, profile='functional'):
    result = context_value.template(text, profile)
    result['attribution_replay'] = structural_attribution(text, profile=profile)
    result.update(audience='STRUCTURAL FIXTURE reader', purpose='Test binding only',
                  whole_text_scan='STRUCTURAL FIXTURE, not a content-value judgment')
    for item in result['items']:
        quote = item['context']
        item.update(quote=quote, without='', with_reading='STRUCTURAL FIXTURE with text',
                    without_reading='STRUCTURAL FIXTURE without text', effect='information',
                    reason='STRUCTURAL FIXTURE, no semantic quality claim', decision='keep')
    return result
