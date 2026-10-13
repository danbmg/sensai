
import unittest

from sensai.guardrails.output_guardrail import SensaiOutputGuard


class TestOutputGuardrail(unittest.TestCase):

    def setUp(self):
        self.guard = SensaiOutputGuard()

    def test_normal_medical_answer(self):
        text = "L'amoxicilline appartient à la famille des pénicillines."
        self.assertEqual(self.guard.check(text), text)

    def test_email_is_masked(self):
        result = self.guard.check(
            "Contact : medecin@example.com"
        )
        self.assertEqual(result, "Contact : [EMAIL_MASQUE]")

    def test_phone_is_masked(self):
        result = self.guard.check(
            "Téléphone : 06 12 34 56 78"
        )
        self.assertEqual(result, "Téléphone : [TELEPHONE_MASQUE]")

    def test_international_phone_is_masked(self):
        result = self.guard.check(
            "Téléphone : +33 6 12 34 56 78"
        )
        self.assertEqual(result, "Téléphone : [TELEPHONE_MASQUE]")

    def test_nir_is_masked(self):
        result = self.guard.check(
            "NIR : 1 90 01 75 123 456 78"
        )
        self.assertEqual(result, "NIR : [NIR_MASQUE]")

    def test_existing_pseudonym_is_preserved(self):
        text = "Le dossier [PATIENT_1] indique une allergie."
        self.assertEqual(self.guard.check(text), text)

    def test_empty_answer(self):
        self.assertEqual(self.guard.check(""), "")

    def test_multiple_sensitive_values(self):
        result = self.guard.check(
            "Contact : test@example.com, téléphone 0612345678."
        )
        self.assertNotIn("test@example.com", result)
        self.assertNotIn("0612345678", result)

    def test_idempotence(self):
        text = "Contact : medecin@example.com"
        once = self.guard.check(text)
        twice = self.guard.check(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
