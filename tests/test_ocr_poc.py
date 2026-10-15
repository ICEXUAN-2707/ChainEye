import json
import tempfile
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tools.ocr_poc import (
    execute,
    offset_points,
    parse_crop,
    parse_pages,
    pixel_to_page_matrix,
    render_inputs,
    run_table,
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

    def test_bad_model_hash_stops_before_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.png"
            input_path.write_bytes(b"not-used-by-the-mocked-runner")
            model_root = root / "models"
            model_root.mkdir()
            manifest = json.loads((ROOT / "data" / "ocr_model_manifest.json").read_text(encoding="utf-8"))
            for model in manifest["models"]:
                if model["role"] in {"text_detection", "text_direction", "text_recognition"}:
                    (model_root / model["name"]).write_bytes(b"wrong model")
            args = Namespace(
                input=input_path,
                pages="1",
                table_crop=None,
                run_ocr=True,
                run_layout=False,
                run_table=False,
                output_dir=root / "output",
                model_root=model_root,
                dpi=144,
            )
            with (
                patch("tools.ocr_poc.package_model_roots", return_value=[]),
                patch("tools.ocr_poc.run_ocr") as inference,
                self.assertRaisesRegex(ValueError, "model integrity check failed"),
            ):
                execute(args)
            inference.assert_not_called()

    def test_image_table_crop_is_written_below_output_dir(self):
        class FakeImage:
            width = 100
            height = 100

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def crop(self, _crop):
                return self

            def save(self, path):
                Path(path).write_bytes(b"generated crop")

        class FakeTableOutput:
            cell_bboxes = []
            logic_points = []
            pred_htmls = []

        class FakeRapidTable:
            def __init__(self, _input):
                pass

            def __call__(self, _path):
                return FakeTableOutput()

        class FakeRapidTableInput:
            def __init__(self, **_kwargs):
                pass

        fake_pil = types.ModuleType("PIL")
        fake_pil.Image = types.SimpleNamespace(open=lambda _path: FakeImage())
        fake_table = types.ModuleType("rapid_table")
        fake_table.ModelType = types.SimpleNamespace(SLANETPLUS="slanet_plus")
        fake_table.RapidTable = FakeRapidTable
        fake_table.RapidTableInput = FakeRapidTableInput

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "source.png"
            input_path.write_bytes(b"original image")
            sibling = root / "source-table.png"
            sibling.write_bytes(b"user file")
            output_dir = root / "output"
            rendered = render_inputs(input_path, [1], 144, output_dir)
            model_paths = {
                "text_detection": root / "det.onnx",
                "text_direction": root / "cls.onnx",
                "text_recognition": root / "rec.onnx",
                "table_structure": root / "table.onnx",
            }
            with patch.dict("sys.modules", {"PIL": fake_pil, "rapid_table": fake_table}):
                run_table(rendered[0]["image_path"], (0, 0, 50, 50), output_dir, model_paths, None)

            self.assertEqual(sibling.read_bytes(), b"user file")
            self.assertEqual((output_dir / "table-crops" / "source-table.png").read_bytes(), b"generated crop")


if __name__ == "__main__":
    unittest.main()
