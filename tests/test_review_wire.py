"""Literary transport preserves judgments and fictional voices without factual defaults."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import review_wire as wire
import context_value
from context_fixture import structural_context


class LiteraryWireTests(unittest.TestCase):
    def test_same_literary_context_record_survives_compaction(self):
        text = '她说这只是候选，不代表已证实收益。'
        full = structural_context(text, 'literary')
        template = context_value.template(text, 'literary')
        small = copy.deepcopy(full)
        for key in wire.META:
            small.pop(key, None)
        for item in small['items']:
            item.pop('context', None); item.pop('without', None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'professional.json'
            path.write_text(json.dumps({'role': 'professional', 'context_review_template': template}))
            expanded = wire.expand_native({'context_review': small}, path)['context_review']
        self.assertEqual(expanded, full)
        self.assertEqual(context_value.validate(expanded, text, 'literary'), [])

    def test_pending_literary_record_is_not_approved_by_codec(self):
        text = '她说这不代表什么。'
        template = context_value.template(text, 'literary')
        expanded = wire.expand(wire.compact(template), template)
        self.assertTrue(context_value.validate(expanded, text, 'literary'))


if __name__ == '__main__':
    unittest.main()
