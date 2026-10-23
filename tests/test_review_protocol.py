"""Synthetic transport-contract tests; never a literary quality score."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import context_value
import source_attribution as attribution
import review_findings


class ReviewProtocolTests(unittest.TestCase):
    def test_role_schema_contains_complete_actual_review_contract(self):
        professional = review_findings.result_schema('professional')
        reader = review_findings.result_schema('reader')
        self.assertTrue({'development_response', 'context_review', 'source_attribution'} <= set(professional['required']))
        self.assertNotIn('reading_response', professional['properties'])
        self.assertTrue({'reading_response', 'attribution_replay'} <= set(reader['required']))
        self.assertNotIn('development_response', reader['properties'])
        self.assertEqual(professional['properties']['source_attribution'], attribution.result_schema())
        self.assertEqual(professional['properties']['context_review'], context_value.result_schema())
        self.assertEqual(reader['properties']['attribution_replay'], attribution.result_schema())

    def fictional(self):
        text = '我没有答应。他转身走了。'
        value = attribution.template(text, '', 'source', 'literary')
        value['whole_text_scan'] = 'The passage contains a fictional narrator, not external testimony.'
        value['items'] = [dict(id='fiction-1', context=text, quote='我没有答应。', kind='fictional-voice',
            speaker='fictional', speaker_basis='', support_quote='', negative_status='confirmed',
            source_scope='not-source-claim', status='pass', basis='A fictional narrator describes his own action.')]
        return text, value

    def test_full_schema_exposes_all_new_item_anchors_and_judgments(self):
        schema = attribution.result_schema()
        self.assertEqual(set(schema['required']), {'whole_text_scan', 'items'})
        fields = schema['properties']['items']['items']
        self.assertEqual(set(fields['required']), {'id', 'context', 'quote', 'kind', 'speaker',
            'speaker_basis', 'support_quote', 'negative_status', 'source_scope', 'status', 'basis'})
        self.assertEqual(set(fields['properties']['kind']['enum']), attribution.KINDS)

    def test_context_schema_reuses_attribution_contract(self):
        schema = context_value.result_schema()
        self.assertIn('attribution_replay', schema['required'])
        self.assertEqual(schema['properties']['attribution_replay'], attribution.result_schema())
        fields = schema['properties']['items']['items']
        self.assertEqual(set(fields['required']), {'id', 'context', 'quote', 'without', 'with_reading',
            'without_reading', 'effect', 'reason', 'decision'})

    def test_fictional_alias_and_negative_are_not_external_testimony(self):
        text, value = self.fictional()
        original = copy.deepcopy(value)
        self.assertEqual(attribution.validate(value, text, '', 'source', 'literary'), [])
        self.assertEqual(value, original)

    def test_alias_does_not_exempt_nonfiction_or_source_claims(self):
        text, value = self.fictional()
        value['items'][0]['kind'] = 'source-fact'
        errors = attribution.validate(value, text, '', 'source', 'literary')
        self.assertTrue(any('source scope' in e for e in errors))
        self.assertTrue(any('unsupported' in e for e in errors))
        self.assertTrue(any('speaker identity' in e for e in errors))

    def test_fictional_mode_does_not_accept_an_unanchored_named_source(self):
        text, value = self.fictional()
        value['items'][0]['speaker'] = 'An external official'
        self.assertTrue(any('speaker identity' in e for e in attribution.validate(value, text, '', 'source', 'literary')))

    def test_new_items_cannot_omit_id_or_context(self):
        for key in ('id', 'context'):
            text, value = self.fictional()
            del value['items'][0][key]
            self.assertTrue(attribution.validate(value, text, '', 'source', 'literary'))

    def test_pure_fiction_cannot_silence_actual_owner_disagreement(self):
        text, value = self.fictional()
        reader = copy.deepcopy(value)
        reader['items'][0]['kind'] = 'source-fact'
        self.assertTrue(attribution.compare(value, reader))

    def test_prompt_declares_empty_template_is_not_missing_dialogue(self):
        self.assertIn('do not invent items merely to fill an empty template', attribution.GUIDANCE)
        self.assertIn('exact context and quote', attribution.GUIDANCE)


if __name__ == '__main__':
    unittest.main()
