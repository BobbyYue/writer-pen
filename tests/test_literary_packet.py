import json
from pathlib import Path
import unittest

import test_lifecycle_guard as guard
import literary_methods
import writing_execution
import writing_lifecycle


class LiteraryPacketTests(unittest.TestCase):
    def setUp(self):
        self.flow = guard.LifecycleGuardTests()
        self.flow.setUp()
        self.addCleanup(self.flow.doCleanups)
        self.flow.linked(complete=False)
        self.batch = self.flow.begin_round()
        self.flow.save_native()

    def packet(self, role):
        return json.loads(Path(self.batch["packets"][role]["path"]).read_text())

    def test_professional_gets_current_rules_without_author_paraphrase(self):
        packet = self.packet("professional")
        self.assertEqual(packet["literary_methods"], literary_methods.method_packet("professional"))
        self.assertEqual(packet["literary_methods"]["guidance"], literary_methods.method_packet("author")["guidance"])
        with writing_lifecycle.session(self.flow.lifecycle) as state:
            self.assertEqual(state["method_sha256"], literary_methods.method_packet("author")["sha256"])

    def test_reader_gets_only_neutral_role_guidance(self):
        packet = self.packet("reader")
        self.assertEqual(packet["literary_methods"], literary_methods.method_packet("reader"))
        self.assertNotIn("literary_intent", packet)
        self.assertNotIn("sources", packet)
        self.assertNotIn("constraints", packet)
        self.assertNotEqual(packet["literary_methods"]["guidance"], literary_methods.method_packet("professional")["guidance"])

    def test_native_dispatch_accepts_exact_generated_role_packets(self):
        packets = {role: item["path"] for role, item in self.batch["packets"].items()}
        number, _, context = writing_execution.prepare_dispatch(self.flow.lifecycle, packets, self.flow.run)
        self.assertEqual(number, 1)
        self.assertEqual(context["draft_id"], "draft:v1")

    def test_reader_guidance_cannot_be_replaced_with_author_rules(self):
        packet = self.packet("reader")
        packet["literary_methods"] = literary_methods.method_packet("author")
        path = self.flow.put_json("reader-contaminated.json", packet)
        packets = {role: item["path"] for role, item in self.batch["packets"].items()}
        packets["reader"] = str(path)
        with self.assertRaises(ValueError):
            writing_execution.prepare_dispatch(self.flow.lifecycle, packets, self.flow.run)


if __name__ == "__main__":
    unittest.main()
