import json
import tempfile
import unittest
from pathlib import Path

from tools.ocr_poc import (
    offset_points,
    parse_crop,
    parse_pages,
    pixel_to_page_matrix,
    sha256_path,
    transform_points,
)


ROOT = Path(__file__).resolve().parents[1]


class OCRPocTests(unittest.TestCase):
    def test_page_parser_is_one_based_sorted_and_deduplicated(self):
        self.assertEqual(parse_pages("3,1-2,2"), [1, 2, 3])
        for invalid in ("0", "3-1", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_pages(invalid)

    def test_table_crop_requires_positive_area(self):
        self.assertEqual(parse_crop("10,20,30,40"), (10, 20, 30, 40))
        self.assertIsNone(parse_crop(None))
        for invalid in ("1,2,3", "10,20,10,40", "-1,0,2,2"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_crop(invalid)

    def test_unrotated_pixel_coordinates_map_to_pdf_points(self):
        matrix = pixel_to_page_matrix(144, 0, [0, 0, 595, 842])
        self.assertEqual(matrix, [0.5, 0.0, 0.0, 0.5, 0.0, 0.0])
        self.assertEqual(transform_points([[0, 0], [200, 100]], matrix), [[0.0, 0.0], [100.0, 50.0]])
        self.assertEqual(offset_points([[1, 2]], 100, 200), [[101.0, 202.0]])

    def test_unverified_page_geometries_fail_closed_instead_of_emitting_false_coordinates(self):
        self.assertIsNone(pixel_to_page_matrix(144, 90, [0, 0, 595, 842]))
        self.assertIsNone(pixel_to_page_matrix(144, 0, [10, 20, 605, 862]))
        self.assertIsNone(transform_points([[1, 2]], None))

    def test_model_manifest_has_unique_roles_and_valid_hashes(self):
        manifest = json.loads((ROOT / "data" / "ocr_model_manifest.json").read_text(encoding="utf-8"))
        roles = [item["role"] for item in manifest["models"]]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertEqual(manifest["profile_id"], "rapidai-cpu-onnx-v1")
        for item in manifest["models"]:
            self.assertEqual(len(item["sha256"]), 64)
            int(item["sha256"], 16)
            self.assertGreater(item["bytes"], 0)
        self.assertEqual(manifest["license_review"]["model_notice_status"], "needs_human_legal_confirmation")

    def test_sha256_reads_streamed_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.bin"
            path.write_bytes(b"chain-eye")
            self.assertEqual(sha256_path(path), "fa55e19d1160a74da8bfd020710763cbeffb9e38d76006126b8ebe31ba700646")


if __name__ == "__main__":
    unittest.main()
