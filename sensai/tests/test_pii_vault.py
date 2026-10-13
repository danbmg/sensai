
import unittest

from sensai.guardrails.pii_vault import SensaiPIIVault


class TestPIIVault(unittest.TestCase):

    def setUp(self):
        self.vault = SensaiPIIVault()

    def test_mask_email(self):
        result = self.vault.mask(
            "Contact : patient@example.com"
        )
        self.assertEqual(result, "Contact : [EMAIL_1]")

    def test_mask_phone(self):
        result = self.vault.mask(
            "Téléphone : 06 12 34 56 78"
        )
        self.assertEqual(
            result,
            "Téléphone : [TELEPHONE_1]",
        )

    def test_mask_nir(self):
        result = self.vault.mask(
            "NIR : 1 90 01 75 123 456 78"
        )
        self.assertEqual(result, "NIR : [NIR_1]")

    def test_mask_birth_date(self):
        result = self.vault.mask(
            "Patiente née le 12/04/1975."
        )
        self.assertEqual(
            result,
            "Patiente née le [NAISSANCE_1].",
        )

    def test_repeated_email_uses_same_placeholder(self):
        first = self.vault.mask("patient@example.com")
        second = self.vault.mask("patient@example.com")

        self.assertEqual(first, "[EMAIL_1]")
        self.assertEqual(second, "[EMAIL_1]")

    def test_different_emails_get_different_placeholders(self):
        first = self.vault.mask("alice@example.com")
        second = self.vault.mask("bob@example.com")

        self.assertEqual(first, "[EMAIL_1]")
        self.assertEqual(second, "[EMAIL_2]")

    def test_reveal(self):
        masked = self.vault.mask(
            "Contact : patient@example.com"
        )

        self.assertEqual(
            self.vault.reveal(masked),
            "Contact : patient@example.com",
        )

    def test_reveal_unknown_placeholder(self):
        self.assertEqual(
            self.vault.reveal("[EMAIL_999]"),
            "[EMAIL_999]",
        )

    def test_reveal_args_nested(self):
        self.vault.mask("patient@example.com")

        args = {
            "patient": "[EMAIL_1]",
            "details": {
                "contacts": ["[EMAIL_1]"],
                "age": 42,
            },
        }

        restored = self.vault.reveal_args(args)

        self.assertEqual(
            restored["patient"],
            "patient@example.com",
        )
        self.assertEqual(
            restored["details"]["contacts"][0],
            "patient@example.com",
        )
        self.assertEqual(restored["details"]["age"], 42)

    def test_export_and_restore_session(self):
        self.vault.mask("patient@example.com")
        saved_map = self.vault.export()

        new_vault = SensaiPIIVault(saved_map)

        self.assertEqual(
            new_vault.reveal("[EMAIL_1]"),
            "patient@example.com",
        )
        self.assertEqual(
            new_vault.mask("autre@example.com"),
            "[EMAIL_2]",
        )

    def test_existing_placeholder_is_preserved(self):
        self.assertEqual(
            self.vault.mask("Patient [EMAIL_1]"),
            "Patient [EMAIL_1]",
        )

    def test_normal_medical_text_is_unchanged(self):
        text = "Le patient présente une allergie à la pénicilline."
        self.assertEqual(self.vault.mask(text), text)

    def test_export_returns_copy(self):
        self.vault.mask("patient@example.com")
        exported = self.vault.export()
        exported.clear()

        self.assertEqual(
            self.vault.reveal("[EMAIL_1]"),
            "patient@example.com",
        )


if __name__ == "__main__":
    unittest.main()
