"""Source propagation and role boundaries, not literary-quality assertions."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import literary_methods as methods


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class LiteraryMethodsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        (self.root / "references").mkdir()
        source = Path(__file__).resolve().parents[1] / 'references/review-coverage.md'
        self.coverage_path = self.root / 'references/review-coverage.md'
        shutil.copyfile(source, self.coverage_path)
        self.coverage = methods._section(source.read_bytes(), '专业审稿必答项')
        self.criteria = "## 共用文学准则\n\nShared judgment alpha.\nCompare support and counterevidence.\n\n"
        self.reader = "## 独立读者回读\n\nWhat did you understand?\nWhat remains uncertain?\n\n"
        self.reaction = ("### 反应的程度是否有支撑\n\nReaction guidance alpha.\n\n"
                         "#### Example\n\nContext matters.\n\n")
        self.review = self.root / "references/literary-review.md"
        self.character = self.root / "references/character-first.md"
        self.review.write_text("# Methods\n\nPrivate setup notes.\n\n" + self.criteria + self.reader +
                               "## Maintenance\n\nPrivate integration notes.\n", encoding="utf-8")
        self.character.write_text("# Characters\n\n## Before drafting\n\nSealed baseline instructions.\n\n" +
                                  self.reaction + "## After drafting\n\nPrivate comparison notes.\n", encoding="utf-8")

    def packet(self, role="professional"):
        return methods.method_packet(role, skill_root=self.root)

    def guidance(self, criteria=None, reaction=None):
        return '\n\n'.join(part.strip() for part in (criteria or self.criteria, reaction or self.reaction, self.coverage))

    def test_default_role_and_exact_section_selection(self):
        packet = methods.method_packet(skill_root=self.root)
        self.assertEqual(packet, self.packet("professional"))
        self.assertEqual(packet["guidance"], self.guidance())
        self.assertEqual(set(packet), {"version", "role", "sources", "guidance", "sha256"})

    def test_file_and_section_hashes_bind_exact_bytes(self):
        packet = self.packet()
        expected = [(self.review, "共用文学准则", self.criteria),
                    (self.character, "反应的程度是否有支撑", self.reaction),
                    (self.coverage_path, '专业审稿必答项', self.coverage)]
        self.assertEqual(len(packet["sources"]), len(expected))
        for source, (path, anchor, section) in zip(packet["sources"], expected):
            self.assertEqual(source, {"path": path.relative_to(self.root).as_posix(),
                                      "sha256": sha(path.read_bytes()), "anchor": anchor,
                                      "section_sha256": sha(section.encode("utf-8"))})

    def test_packet_hash_can_be_recomputed_from_returned_payload(self):
        for role in ("author", "professional", "reader"):
            packet = self.packet(role)
            recorded = packet.pop("sha256")
            raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.assertEqual(recorded, sha(raw))
            self.assertEqual(packet["version"], 1)

    def test_deterministic_across_calls_and_local_copies(self):
        packet = self.packet()
        self.assertEqual(packet, self.packet())
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        copied_root = Path(directory.name)
        shutil.copytree(self.root / "references", copied_root / "references")
        self.assertEqual(packet, methods.method_packet(skill_root=copied_root))

    def test_author_and_professional_share_source_not_role_digest(self):
        author, professional = self.packet("author"), self.packet("professional")
        self.assertEqual(author["guidance"], professional["guidance"])
        self.assertEqual(author["sources"], professional["sources"])
        self.assertNotEqual(author["sha256"], professional["sha256"])

    def test_init_fingerprint_uses_same_role_and_pinned_source_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        pinned = Path(directory.name)
        shutil.copytree(self.root / "references", pinned / "references")
        initial = methods.method_packet("author", skill_root=pinned)["sha256"]
        self.review.write_text(self.review.read_text(encoding="utf-8").replace("alpha", "upgrade"), encoding="utf-8")
        self.assertEqual(initial, methods.method_packet("author", skill_root=pinned)["sha256"])
        self.assertNotEqual(initial, self.packet("author")["sha256"])
        authority = pinned / "references/character-first.md"
        authority.write_text(authority.read_text(encoding="utf-8").replace("alpha", "changed"), encoding="utf-8")
        self.assertNotEqual(initial, methods.method_packet("author", skill_root=pinned)["sha256"])

    def test_criteria_update_propagates_without_import_reload_or_version_bump(self):
        before = {role: self.packet(role) for role in ("author", "professional")}
        updated = self.criteria.replace("alpha", "beta")
        self.review.write_text(self.review.read_text(encoding="utf-8").replace(self.criteria, updated), encoding="utf-8")
        for role, previous in before.items():
            current = self.packet(role)
            self.assertEqual(current["guidance"], self.guidance(criteria=updated))
            self.assertEqual(current["version"], previous["version"])
            self.assertNotEqual(current["sha256"], previous["sha256"])
            self.assertNotEqual(current["sources"][0], previous["sources"][0])
            self.assertEqual(current["sources"][1], previous["sources"][1])

    def test_authoritative_reaction_update_reaches_both_roles_but_not_reader(self):
        before = {role: self.packet(role) for role in ("author", "professional", "reader")}
        updated = self.reaction.replace("alpha", "beta")
        self.character.write_text(self.character.read_text(encoding="utf-8").replace(self.reaction, updated), encoding="utf-8")
        for role in ("author", "professional"):
            current = self.packet(role)
            self.assertEqual(current["guidance"], self.guidance(reaction=updated))
            self.assertNotEqual(current["sha256"], before[role]["sha256"])
            self.assertEqual(current["sources"][0], before[role]["sources"][0])
            self.assertNotEqual(current["sources"][1]["sha256"], before[role]["sources"][1]["sha256"])
            self.assertEqual(current["sources"][1]["section_sha256"], sha(updated.encode("utf-8")))
        self.assertEqual(self.packet("reader"), before["reader"])

    def test_file_provenance_changes_even_outside_selected_section(self):
        before = self.packet()
        self.character.write_text(self.character.read_text(encoding="utf-8").replace(
            "Sealed baseline instructions.", "Updated sealing procedure."), encoding="utf-8")
        current = self.packet()
        self.assertEqual(current["guidance"], before["guidance"])
        self.assertEqual(current["sources"][1]["section_sha256"], before["sources"][1]["section_sha256"])
        self.assertNotEqual(current["sources"][1]["sha256"], before["sources"][1]["sha256"])
        self.assertNotEqual(current["sha256"], before["sha256"])

    def test_reader_is_exact_neutral_section_not_author_answers(self):
        before = self.packet("reader")
        self.review.write_text(self.review.read_text(encoding="utf-8").replace(
            "Shared judgment alpha.", "Author intention: secretly admire Pat. Expected answer: Pat is noble."), encoding="utf-8")
        current = self.packet("reader")
        self.assertEqual(current["guidance"], self.reader.strip())
        self.assertEqual(current["guidance"], before["guidance"])
        self.assertEqual(len(current["sources"]), 1)
        self.assertEqual(current["sources"][0]["path"], "references/literary-review.md")
        self.assertEqual(current["sources"][0]["section_sha256"], sha(self.reader.encode("utf-8")))
        self.assertEqual(set(current), {"version", "role", "sources", "guidance", "sha256"})

    def test_reader_questions_update_independently(self):
        before = self.packet("reader")
        updated = self.reader.replace("What remains uncertain?", "Where did your understanding change?")
        self.review.write_text(self.review.read_text(encoding="utf-8").replace(self.reader, updated), encoding="utf-8")
        current = self.packet("reader")
        self.assertEqual(current["guidance"], updated.strip())
        self.assertNotEqual(current["sha256"], before["sha256"])
        self.assertEqual(self.packet()["guidance"], self.guidance())

    def test_reader_does_not_require_character_or_professional_section(self):
        self.character.unlink()
        self.review.write_text("# Readback\n\n" + self.reader, encoding="utf-8")
        self.assertEqual(self.packet("reader")["guidance"], self.reader.strip())
        with self.assertRaises(ValueError):
            self.packet("professional")

    def test_unknown_roles_rejected_before_any_file_read(self):
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("Unexpected read")):
            for role in ("", "Professional", "reviewer", None, 0, [], {}):
                with self.subTest(role=role), self.assertRaises(ValueError):
                    self.packet(role)

    def test_missing_source_never_falls_back_to_installed_skill(self):
        self.character.unlink()
        for role in ("author", "professional"):
            with self.subTest(role=role), self.assertRaises(FileNotFoundError):
                self.packet(role)
        self.review.unlink()
        with self.assertRaises(FileNotFoundError):
            self.packet("reader")

    def test_missing_duplicate_or_empty_authoritative_section_fails(self):
        for contents in ("# Other instructions\n", self.reaction + self.reaction,
                         "### 反应的程度是否有支撑\n\n## Next\nOther guidance.\n"):
            self.character.write_text(contents, encoding="utf-8")
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                self.packet()

    def test_fenced_heading_examples_do_not_change_section_selection(self):
        example = "```markdown\n### 反应的程度是否有支撑\nExample, not a criterion.\n```\n\n"
        raw = self.character.read_text(encoding="utf-8")
        self.character.write_text(example + raw, encoding="utf-8")
        self.assertEqual(self.packet()["guidance"], self.guidance())

    def test_source_hashes_preserve_crlf_bytes(self):
        raw = self.character.read_bytes().replace(b"\n", b"\r\n")
        self.character.write_bytes(raw)
        packet = self.packet()
        self.assertEqual(packet["sources"][1]["sha256"], sha(raw))
        section = self.reaction.replace("\n", "\r\n")
        self.assertEqual(packet["sources"][1]["section_sha256"], sha(section.encode("utf-8")))
        self.assertEqual(packet["guidance"], self.guidance(reaction=section))

    def test_local_read_only_and_no_network(self):
        files = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        read_bytes, reads = Path.read_bytes, []

        def read(path):
            reads.append(path)
            return read_bytes(path)

        with mock.patch.object(Path, "read_bytes", read), mock.patch("socket.socket", side_effect=AssertionError("Network access")):
            for role in ("author", "professional", "reader"):
                self.packet(role)
        self.assertEqual(reads, [self.coverage_path, self.review, self.character, self.coverage_path,
                                self.coverage_path, self.review, self.character, self.coverage_path, self.review])
        self.assertEqual({path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}, files)

    def test_source_symlink_cannot_escape_selected_skill_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        outside = Path(directory.name) / "character-first.md"
        outside.write_bytes(self.character.read_bytes())
        self.character.unlink()
        self.character.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.packet()
        self.assertEqual(self.packet("reader")["guidance"], self.reader.strip())

    def test_caller_mutation_does_not_contaminate_future_packets(self):
        original = self.packet()
        changed = self.packet()
        changed["sources"][0]["sha256"] = "forged"
        changed["guidance"] = "Author supplied replacement"
        self.assertEqual(self.packet(), original)

    def test_default_root_reads_staged_sources_and_excludes_full_references(self):
        root = Path(__file__).resolve().parents[1]
        packet = methods.method_packet()
        self.assertEqual([item["path"] for item in packet["sources"]],
                         ["references/literary-review.md", "references/character-first.md", "references/review-coverage.md"])
        for source in packet["sources"]:
            self.assertEqual(source["sha256"], sha((root / source["path"]).read_bytes()))
        full_text = "\n\n".join((root / source["path"]).read_text(encoding="utf-8") for source in packet["sources"])
        self.assertLess(len(packet["guidance"]), len(full_text))
        self.assertEqual(methods.method_packet("author")["guidance"], packet["guidance"])
        self.assertLess(len(methods.method_packet("reader")["guidance"]), len(packet["guidance"]))


if __name__ == "__main__":
    unittest.main()
