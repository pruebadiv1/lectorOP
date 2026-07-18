import unittest
from pathlib import Path

from app.parser import parse_winmaker_pdf


DOWNLOADS = Path.home() / "Downloads"


class WinmakerParserRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.samples = {
            "solsona": DOWNLOADS / "SEBASTIAN SOLSONA.pdf",
            "torres": DOWNLOADS / "MARCELO TORRES- CASA 1 Y 2 LOTEO SOMMADOSI.pdf",
            "lenan": DOWNLOADS / "LENAN PLANTA BAJA.pdf",
        }
        missing = [str(path) for path in cls.samples.values() if not path.exists()]
        if missing:
            raise unittest.SkipTest(f"Faltan PDFs de regresión: {', '.join(missing)}")

    def test_expected_page_and_row_counts(self) -> None:
        expected = {
            "solsona": (11, 14, 121),
            "torres": (10, 16, 170),
            "lenan": (15, 31, 251),
        }
        for name, path in self.samples.items():
            with self.subTest(name=name):
                result = parse_winmaker_pdf(path, name)
                typologies = result["typologies"]
                self.assertEqual(expected[name][0], len(typologies))
                self.assertEqual(expected[name][1], sum(len(item["glasses"]) for item in typologies))
                self.assertEqual(expected[name][2], sum(len(item["accessories"]) for item in typologies))

    def test_glass_quantity_is_preserved_without_expansion(self) -> None:
        result = parse_winmaker_pdf(self.samples["torres"], "Marcelo Torres")
        glasses = result["typologies"][0]["glasses"]
        self.assertEqual(1, len(glasses))
        self.assertEqual(3, glasses[0]["quantity_final"])
        self.assertEqual("967 x 2043", glasses[0]["measure_final"])

    def test_duplicate_glass_rows_remain_independent(self) -> None:
        result = parse_winmaker_pdf(self.samples["solsona"], "Solsona")
        glasses = result["typologies"][9]["glasses"]
        duplicates = [item for item in glasses if item["measure_final"] == "430 x 682"]
        self.assertEqual(2, len(duplicates))
        self.assertNotEqual(duplicates[0]["id"], duplicates[1]["id"])

    def test_tela_is_preserved_as_editable_material(self) -> None:
        result = parse_winmaker_pdf(self.samples["solsona"], "Solsona")
        meshes = [
            glass
            for typology in result["typologies"]
            for glass in typology["glasses"]
            if glass["material_type"] == "mesh"
        ]
        self.assertEqual(4, len(meshes))
        self.assertTrue(all(item["status"] == "detected" for item in meshes))
        self.assertTrue(all(item["excluded"] is False for item in meshes))

    def test_fragmented_accessory_codes_are_reconstructed(self) -> None:
        result = parse_winmaker_pdf(self.samples["torres"], "Marcelo Torres")
        codes = {item["code"] for item in result["typologies"][0]["accessories"]}
        self.assertIn("R49", codes)
        self.assertIn("H57", codes)

    def test_corrupt_text_is_flagged(self) -> None:
        result = parse_winmaker_pdf(self.samples["lenan"], "Lenan")
        item = next(
            accessory
            for accessory in result["typologies"][9]["accessories"]
            if accessory["code"] == "B68"
        )
        self.assertEqual("low", item["confidence"])
        self.assertFalse(item["reviewed"])


if __name__ == "__main__":
    unittest.main()
