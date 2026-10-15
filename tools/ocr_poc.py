"""Reproducible G7 OCR proof-of-concept runner.

This is an evaluation tool, not the production parser. It never reads answer
labels and it never writes Dataset facts or changes review status.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".runtime" / "ocr-poc" / "runs"
PACKAGE_NAMES = ("rapidocr", "rapid-table", "rapid-layout", "onnxruntime")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pages(value: str) -> list[int]:
    """Parse one-based page expressions such as ``1,3-5``."""
    pages: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"descending page range: {item}")
            pages.update(range(start, end + 1))
        else:
            pages.add(int(item))
    if not pages or min(pages) < 1:
        raise ValueError("pages must contain positive one-based page numbers")
    return sorted(pages)


def parse_crop(value: str | None) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = tuple(int(part.strip()) for part in value.split(","))
    if len(parts) != 4 or parts[0] < 0 or parts[1] < 0 or parts[2] <= parts[0] or parts[3] <= parts[1]:
        raise ValueError("table crop must be x0,y0,x1,y1 with positive area")
    return parts


def pixel_to_page_matrix(dpi: int, rotation: int, cropbox: Sequence[float]) -> list[float] | None:
    """Return a six-value affine for the controlled, unrotated POC path.

    Rotation handling deliberately fails closed here. G7.2 must implement and
    test all PDF rotations before these coordinates enter product evidence.
    """
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if rotation % 360 != 0 or float(cropbox[0]) != 0.0 or float(cropbox[1]) != 0.0:
        return None
    scale = 72.0 / dpi
    return [scale, 0.0, 0.0, scale, 0.0, 0.0]


def transform_points(points: Iterable[Sequence[float]], matrix: Sequence[float] | None) -> list[list[float]] | None:
    if matrix is None:
        return None
    a, b, c, d, e, f = matrix
    return [[round(a * float(x) + c * float(y) + e, 4), round(b * float(x) + d * float(y) + f, 4)] for x, y in points]


def rectangle_points(box: Sequence[float]) -> list[list[float]]:
    x0, y0, x1, y1 = (float(value) for value in box)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def offset_points(points: Iterable[Sequence[float]], x_offset: float, y_offset: float) -> list[list[float]]:
    return [[float(x) + x_offset, float(y) + y_offset] for x, y in points]


def package_versions() -> dict[str, str]:
    versions = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def render_inputs(input_path: Path, pages: list[int], dpi: int, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if input_path.suffix.casefold() != ".pdf":
        if pages != [1]:
            raise ValueError("image input supports only page 1")
        return [{
            "page_no": 1,
            "image_path": input_path,
            "geometry": None,
            "pixel_to_page_matrix": None,
            "warnings": ["image input has no trustworthy PDF coordinate transform"],
        }]

    import fitz

    rendered = []
    with fitz.open(input_path) as document:
        for page_no in pages:
            if page_no > document.page_count:
                raise ValueError(f"page {page_no} exceeds PDF page count {document.page_count}")
            page = document[page_no - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
            image_path = output_dir / f"page-{page_no:04d}.png"
            pixmap.save(image_path)
            cropbox = [page.cropbox.x0, page.cropbox.y0, page.cropbox.x1, page.cropbox.y1]
            matrix = pixel_to_page_matrix(dpi, page.rotation, cropbox)
            warnings = ["PDF text-layer page was rasterized; this is not a real scanned-document sample"]
            if matrix is None:
                warnings.append("rotation or non-zero crop origin is unsupported in the G7.0 POC; PDF coordinates are null")
            rendered.append({
                "page_no": page_no,
                "image_path": image_path,
                "geometry": {
                    "width_pt": round(page.rect.width, 4),
                    "height_pt": round(page.rect.height, 4),
                    "rotation": page.rotation,
                    "cropbox": cropbox,
                    "image_width_px": pixmap.width,
                    "image_height_px": pixmap.height,
                },
                "pixel_to_page_matrix": matrix,
                "warnings": warnings,
            })
    return rendered


def ocr_model_params(model_paths: dict[str, Path]) -> dict:
    return {
        "Det.model_path": str(model_paths["text_detection"]),
        "Cls.model_path": str(model_paths["text_direction"]),
        "Rec.model_path": str(model_paths["text_recognition"]),
        "Global.log_level": "warning",
        "EngineConfig.onnxruntime.intra_op_num_threads": 2,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    }


def run_ocr(image_path: Path, model_paths: dict[str, Path], matrix: Sequence[float] | None) -> dict:
    from rapidocr import RapidOCR

    params = ocr_model_params(model_paths)
    started = time.perf_counter()
    engine = RapidOCR(params=params)
    initialized = time.perf_counter()
    output = engine(str(image_path))
    finished = time.perf_counter()
    boxes = output.boxes.tolist() if hasattr(output.boxes, "tolist") else list(output.boxes or [])
    texts = list(output.txts or [])
    scores = output.scores.tolist() if hasattr(output.scores, "tolist") else list(output.scores or [])
    lines = []
    for box, text, score in zip(boxes, texts, scores):
        polygon = [[float(x), float(y)] for x, y in box]
        lines.append({
            "text": text,
            "score": round(float(score), 6),
            "polygon_px": polygon,
            "polygon_pdf": transform_points(polygon, matrix),
        })
    return {
        "config": params,
        "init_seconds": round(initialized - started, 3),
        "inference_seconds": round(finished - initialized, 3),
        "line_count": len(lines),
        "lines": lines,
    }


def run_layout(image_path: Path, model_path: Path, matrix: Sequence[float] | None) -> dict:
    from rapid_layout import RapidLayout

    started = time.perf_counter()
    engine = RapidLayout(
        model_type="pp_doc_layoutv3",
        model_dir_or_path=str(model_path),
        conf_thresh=0.5,
        iou_thresh=0.5,
    )
    initialized = time.perf_counter()
    output = engine(str(image_path))
    finished = time.perf_counter()
    regions = []
    for box, class_name, score in zip(output.boxes or [], output.class_names or [], output.scores or []):
        polygon = rectangle_points(box)
        regions.append({
            "class_name": class_name,
            "score": round(float(score), 6),
            "bbox_px": [float(value) for value in box],
            "polygon_pdf": transform_points(polygon, matrix),
        })
    return {
        "model_type": "pp_doc_layoutv3",
        "init_seconds": round(initialized - started, 3),
        "inference_seconds": round(finished - initialized, 3),
        "region_count": len(regions),
        "regions": regions,
    }


def run_table(
    image_path: Path,
    crop: tuple[int, int, int, int],
    output_dir: Path,
    model_paths: dict[str, Path],
    matrix: Sequence[float] | None,
) -> dict:
    from PIL import Image
    from rapid_table import ModelType, RapidTable, RapidTableInput

    x0, y0, x1, y1 = crop
    with Image.open(image_path) as image:
        if x1 > image.width or y1 > image.height:
            raise ValueError(f"table crop {crop} exceeds image size {(image.width, image.height)}")
        cropped = image.crop(crop)
        crop_dir = output_dir / "table-crops"
        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / f"{image_path.stem}-table.png"
        cropped.save(crop_path)
    started = time.perf_counter()
    engine = RapidTable(RapidTableInput(
        model_type=ModelType.SLANETPLUS,
        model_dir_or_path=str(model_paths["table_structure"]),
        ocr_params=ocr_model_params(model_paths),
    ))
    initialized = time.perf_counter()
    output = engine(str(crop_path))
    finished = time.perf_counter()
    cells = []
    raw_boxes = output.cell_bboxes[0].tolist() if output.cell_bboxes else []
    logic_points = output.logic_points[0].tolist() if output.logic_points else []
    for box, logic in zip(raw_boxes, logic_points):
        local_points = [[float(box[index]), float(box[index + 1])] for index in range(0, len(box), 2)]
        page_points = offset_points(local_points, x0, y0)
        cells.append({
            "logic_point": [int(value) for value in logic],
            "polygon_crop_px": local_points,
            "polygon_page_px": page_points,
            "polygon_pdf": transform_points(page_points, matrix),
        })
    return {
        "model_type": "slanet_plus",
        "crop_px": list(crop),
        "crop_sha256": sha256_path(crop_path),
        "init_seconds": round(initialized - started, 3),
        "inference_seconds": round(finished - initialized, 3),
        "cell_count": len(cells),
        "html": output.pred_htmls[0] if output.pred_htmls else None,
        "cells": cells,
    }


def package_model_roots() -> list[Path]:
    roots = []
    for package_name in ("rapidocr", "rapid_table", "rapid_layout"):
        spec = importlib.util.find_spec(package_name)
        if spec is not None and spec.origin is not None:
            roots.append(Path(spec.origin).resolve().parent / "models")
    return roots


def download_model_file(expected: dict, destination: Path) -> None:
    """Download one model without exposing it to an inference engine first."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".download",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            with urllib.request.urlopen(expected["source"], timeout=120) as response:
                shutil.copyfileobj(response, stream)
        actual = (temporary_path.stat().st_size, sha256_path(temporary_path))
        wanted = (expected["bytes"], expected["sha256"])
        if actual != wanted:
            raise ValueError(f"downloaded model integrity check failed: {expected['name']}")
        temporary_path.replace(destination)
        temporary_path = None
    except (OSError, urllib.error.URLError) as exc:
        raise ValueError(f"failed to download required model: {expected['name']}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def verify_model_files(
    search_roots: Iterable[Path],
    model_root: Path,
    required_roles: set[str],
) -> tuple[list[dict], dict[str, Path]]:
    manifest = json.loads((ROOT / "data" / "ocr_model_manifest.json").read_text(encoding="utf-8"))
    verified = []
    selected_paths = {}
    manifest_roles = {item["role"] for item in manifest["models"]}
    unknown_roles = required_roles - manifest_roles
    if unknown_roles:
        raise ValueError(f"model manifest does not define roles: {sorted(unknown_roles)}")
    roots = [root.resolve() for root in search_roots]
    for expected in manifest["models"]:
        if expected["role"] not in required_roles:
            continue
        candidates = []
        seen = set()
        for root in roots:
            if root.exists():
                for path in sorted(root.rglob(expected["name"])):
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(resolved)
        if not candidates:
            destination = model_root.resolve() / expected["name"]
            download_model_file(expected, destination)
            candidates.append(destination)
        actuals = {(path.stat().st_size, sha256_path(path)) for path in candidates}
        wanted = (expected["bytes"], expected["sha256"])
        if actuals != {wanted}:
            raise ValueError(f"model integrity check failed: {expected['name']}")
        selected_paths[expected["role"]] = candidates[0]
        verified.append({
            "role": expected["role"],
            "name": expected["name"],
            "bytes": expected["bytes"],
            "sha256": expected["sha256"],
            "copies_found": len(candidates),
        })
    return verified, selected_paths


def required_model_roles(args: argparse.Namespace) -> set[str]:
    roles = set()
    if args.run_ocr:
        roles.update(("text_detection", "text_direction", "text_recognition"))
    if args.run_layout:
        roles.add("document_layout")
    if args.run_table:
        roles.add("table_structure")
        roles.update(("text_detection", "text_direction", "text_recognition"))
    return roles


def execute(args: argparse.Namespace) -> dict:
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    pages = parse_pages(args.pages)
    crop = parse_crop(args.table_crop)
    if args.run_table and crop is None:
        raise ValueError("--run-table requires --table-crop")
    output_dir = args.output_dir.resolve()
    model_root = args.model_root.resolve()
    models, model_paths = verify_model_files(
        [model_root, *package_model_roots()],
        model_root,
        required_model_roles(args),
    )
    rendered = render_inputs(input_path, pages, args.dpi, output_dir)
    page_results = []
    for item in rendered:
        result = {
            "page_no": item["page_no"],
            "render_sha256": sha256_path(item["image_path"]),
            "geometry": item["geometry"],
            "pixel_to_page_matrix": item["pixel_to_page_matrix"],
            "warnings": item["warnings"],
        }
        if args.run_ocr:
            result["ocr"] = run_ocr(item["image_path"], model_paths, item["pixel_to_page_matrix"])
        if args.run_layout:
            result["layout"] = run_layout(
                item["image_path"],
                model_paths["document_layout"],
                item["pixel_to_page_matrix"],
            )
        if args.run_table:
            result["table"] = run_table(
                item["image_path"],
                crop,
                output_dir,
                model_paths,
                item["pixel_to_page_matrix"],
            )
        page_results.append(result)
    return {
        "schema_version": 1,
        "purpose": "evaluation_only",
        "input": {"path": str(input_path), "sha256": sha256_path(input_path)},
        "configuration": {
            "dpi": args.dpi,
            "pages": pages,
            "run_ocr": args.run_ocr,
            "run_layout": args.run_layout,
            "run_table": args.run_table,
            "table_crop": list(crop) if crop else None,
        },
        "packages": package_versions(),
        "models": models,
        "pages": page_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated G7 RapidAI OCR POC and write auditable JSON.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--pages", default="1", help="One-based pages, for example 1,3-5")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model-root", type=Path, default=ROOT / ".runtime" / "ocr-poc" / "models")
    parser.add_argument("--run-ocr", action="store_true")
    parser.add_argument("--run-layout", action="store_true")
    parser.add_argument("--run-table", action="store_true")
    parser.add_argument("--table-crop", help="Table crop in rendered pixels: x0,y0,x1,y1")
    parser.add_argument("--result", type=Path, help="JSON output; defaults to <output-dir>/result.json")
    args = parser.parse_args()
    if args.dpi <= 0:
        parser.error("--dpi must be positive")
    try:
        result = execute(args)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    result_path = (args.result or args.output_dir / "result.json").resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "result": str(result_path), "pages": len(result["pages"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
