from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import cv2
import numpy as np

from app.core.config import settings
from app.services.template_config import load_template

try:  # pragma: no cover
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover
    PaddleOCR = None


NUMERIC_FIELDS = {
    "grey_width",
    "epi_on_table",
    "meters_per_120_yards",
    "total_ends",
    "epi_difference",
    "reed_space",
    "warp_crimp_percent",
    "weight_warp1",
    "cost_warp1",
    "composition_warp1",
    "weight_weft1",
    "cost_weft1",
    "composition_weft1",
    "gsm_total_yarn_cost",
    "fabric_total_yarn_cost",
    "fabric_weight_glm_inc_sizing",
    "particulars_total_cost",
    "total_price",
    "target_price",
    "weaving_charge_as_per_tp",
    "order_quantity",
    "yarn_requirement_warp1",
    "yarn_requirement_weft1",
    "yarn_requirement_total",
    "cover_factor"
}

CHECKBOX_FIELDS = {
    "is_warp_butta",
    "is_weft_butta",
    "is_warp2_sizing_count",
    "is_seersucker"
}


@dataclass
class FieldResult:
    field_name: str
    value: Any
    raw_text: str
    confidence: float
    issues: list[str]
    bbox: dict[str, float]


@dataclass
class OcrToken:
    text: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


class DomesticCostingExtractor:
    def __init__(self) -> None:
        self.template = load_template()
        if PaddleOCR:
            det_dir = settings.ocr_model_root / "det"
            rec_dir = settings.ocr_model_root / "rec"
            cls_dir = settings.ocr_model_root / "cls"
            for directory in [det_dir, rec_dir, cls_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            self.ocr = PaddleOCR(
                use_textline_orientation=False,
                lang="en",
                det_model_dir=str(det_dir),
                rec_model_dir=str(rec_dir),
                cls_model_dir=str(cls_dir),
            )
        else:
            self.ocr = None

    def extract(self, image_path: str | Path) -> tuple[dict[str, Any], list[FieldResult], float, list[str]]:
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(f"Could not read image: {image_path}")

        aligned = self._align_to_template(image)
        tokens = self._extract_tokens(aligned)
        field_results: list[FieldResult] = []
        issues: list[str] = []

        for field_name, field_cfg in self.template["fields"].items():
            result = self._extract_field(aligned, tokens, field_name, field_cfg)
            field_results.append(result)
            issues.extend(f"{field_name}: {issue}" for issue in result.issues)

        data = {result.field_name: result.value for result in field_results}
        data = self._apply_structured_overrides(tokens, data)
        field_results = [
            FieldResult(
                field_name=result.field_name,
                value=data.get(result.field_name),
                raw_text=result.raw_text if data.get(result.field_name) == result.value else ("" if data.get(result.field_name) is None else str(data.get(result.field_name))),
                confidence=result.confidence,
                issues=result.issues,
                bbox=result.bbox,
            )
            for result in field_results
        ]
        confidence = float(np.mean([result.confidence for result in field_results])) if field_results else 0.0
        issues = self._recompute_issues(data)
        issues.extend(self._cross_validate(data))
        if issues:
            confidence = min(confidence, 0.79)
        else:
            critical_fields = [
                "date",
                "agent",
                "customer",
                "quality",
                "warp_count",
                "weft_count",
                "grey_width",
                "epi_on_table",
                "total_price",
                "target_price",
                "order_quantity",
            ]
            coverage = sum(1 for field in critical_fields if data.get(field) not in (None, "")) / len(critical_fields)
            confidence = max(confidence, 0.82 + (0.16 * coverage))

        return data, field_results, confidence, issues

    def _align_to_template(self, image: np.ndarray) -> np.ndarray:
        return cv2.resize(image, tuple(self.template["reference_size"]))

    def _extract_field(self, image: np.ndarray, tokens: list[OcrToken], field_name: str, field_cfg: dict[str, Any]) -> FieldResult:
        crop, bbox = self._crop_relative(image, field_cfg["bbox"])
        if field_name in CHECKBOX_FIELDS or field_cfg["type"] == "checkbox":
            value, confidence = self._detect_checkbox(crop)
            return FieldResult(field_name, value, str(value), confidence, [], bbox)

        raw_text, confidence = self._read_field_text(tokens, bbox)
        if not raw_text:
            raw_text, confidence = self._run_ocr(crop)
        normalized, issues = self._normalize_value(field_name, raw_text, field_cfg)
        return FieldResult(field_name, normalized, raw_text, confidence, issues, bbox)

    def _extract_tokens(self, image: np.ndarray) -> list[OcrToken]:
        if self.ocr is None:
            return []
        try:
            result = self.ocr.ocr(image, cls=False)
        except TypeError:
            result = self.ocr.ocr(image)

        tokens: list[OcrToken] = []
        lines = result[0] if result and result[0] else []
        for line in lines:
            if not line or len(line) < 2:
                continue
            box = line[0]
            text = line[1][0] if len(line[1]) > 0 else ""
            confidence = float(line[1][1]) if len(line[1]) > 1 else 0.0
            if not text or not text.strip():
                continue
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            tokens.append(
                OcrToken(
                    text=text.strip(),
                    confidence=confidence,
                    x1=min(xs),
                    y1=min(ys),
                    x2=max(xs),
                    y2=max(ys),
                )
            )
        return tokens

    def _apply_structured_overrides(self, tokens: list[OcrToken], data: dict[str, Any]) -> dict[str, Any]:
        data = dict(data)
        data.update(self._parse_yarn_table(tokens))
        data.update(self._parse_grey_panel(tokens))
        data.update(self._parse_weight_panel(tokens))
        data.update(self._parse_particulars_panel(tokens))
        data.update(self._parse_price_panel(tokens))
        return data

    def _parse_yarn_table(self, tokens: list[OcrToken]) -> dict[str, Any]:
        region = (80, 540, 1070, 700)
        table_tokens = self._tokens_in_region(tokens, *region)
        rows = {
            "warp": self._find_token_by_text(table_tokens, ["warp count1", "warp count"]),
            "weft": self._find_token_by_text(table_tokens, ["weft count1", "weft count"]),
        }
        columns = {
            "count": 280,
            "rate_per_kg": 367,
            "rate_incl_gst": 451,
            "gst": 549,
            "content": 633,
            "yarn_type": 705,
            "mill": 789,
            "epi_on_loom": 863,
            "ppi": 953,
        }
        output: dict[str, Any] = {}
        for prefix, anchor in rows.items():
            if not anchor:
                continue
            row_tokens = [token for token in table_tokens if abs(token.cy - anchor.cy) <= 20 and token.cx > anchor.cx]
            output[f"{prefix}_count"] = self._token_number_near(row_tokens, columns["count"])
            output[f"{prefix}_rate_per_kg"] = self._token_number_near(row_tokens, columns["rate_per_kg"])
            output[f"{prefix}_rate_incl_gst"] = self._token_number_near(row_tokens, columns["rate_incl_gst"])
            output[f"{prefix}_gst"] = self._token_number_near(row_tokens, columns["gst"])
            output[f"{prefix}_content"] = self._token_text_near(row_tokens, columns["content"], 55)
            output[f"{prefix}_yarn_type"] = self._token_text_near(row_tokens, columns["yarn_type"], 55)
            output[f"{prefix}_mill"] = self._token_text_near(row_tokens, columns["mill"], 55)
            if prefix == "warp":
                output[f"{prefix}_epi_on_loom"] = self._token_number_near(row_tokens, columns["epi_on_loom"])
            output[f"{prefix}_ppi"] = self._token_number_near(row_tokens, columns["ppi"])
        return output

    def _parse_grey_panel(self, tokens: list[OcrToken]) -> dict[str, Any]:
        region_tokens = self._tokens_in_region(tokens, 1110, 520, 1780, 700)
        mappings = {
            "grey_width": ["grey width"],
            "epi_on_table": ["epi on table"],
            "meters_per_120_yards": ["meters per 120", "yards"],
            "total_ends": ["total ends"],
            "epi_difference": ["epi difference"],
            "reed_space": ["reed space"],
            "warp_crimp_percent": ["warp crimp"],
        }
        output: dict[str, Any] = {}
        for field, labels in mappings.items():
            anchor = self._find_token_by_text(region_tokens, labels)
            output[field] = self._token_number_to_right(region_tokens, anchor, 220) if anchor else None
        return output

    def _parse_weight_panel(self, tokens: list[OcrToken]) -> dict[str, Any]:
        region_tokens = self._tokens_in_region(tokens, 70, 820, 500, 1260)
        output: dict[str, Any] = {}
        warp_anchor = self._find_token_by_text(region_tokens, ["warp1"])
        weft_anchor = self._find_token_by_text(region_tokens, ["weft1"])
        gsm_anchor = self._find_token_by_text(region_tokens, ["gsm", "total yarn"])
        fabric_anchor = self._find_token_by_text(region_tokens, ["fabric weight"])
        if warp_anchor:
            row_tokens = [t for t in region_tokens if abs(t.cy - warp_anchor.cy) <= 18 and t.cx > warp_anchor.cx]
            output["weight_warp1"] = self._token_number_near(row_tokens, 220)
            output["cost_warp1"] = self._token_number_near(row_tokens, 308)
            output["composition_warp1"] = self._token_number_near(row_tokens, 370)
        if weft_anchor:
            row_tokens = [t for t in region_tokens if abs(t.cy - weft_anchor.cy) <= 18 and t.cx > weft_anchor.cx]
            output["weight_weft1"] = self._token_number_near(row_tokens, 220)
            output["cost_weft1"] = self._token_number_near(row_tokens, 308)
            output["composition_weft1"] = self._token_number_near(row_tokens, 370)
        if gsm_anchor:
            row_tokens = [t for t in region_tokens if 945 <= t.cy <= 990]
            output["gsm_total_yarn_cost"] = self._token_number_near(row_tokens, 214)
            output["fabric_total_yarn_cost"] = self._token_number_near(row_tokens, 309)
        if fabric_anchor:
            row_tokens = [t for t in region_tokens if 1030 <= t.cy <= 1085]
            output["fabric_weight_glm_inc_sizing"] = self._token_number_near(row_tokens, 214)
        return output

    def _parse_particulars_panel(self, tokens: list[OcrToken]) -> dict[str, Any]:
        region_tokens = self._tokens_in_region(tokens, 520, 790, 1380, 1300)
        row_specs = {
            "sizing_per_kg": ["sizing per kg"],
            "weaving_charges": ["weaving charges"],
            "freight": ["freight per kg", "freight per kg & mtr"],
            "butta_cutting": ["butta cutting per mtr"],
            "yarn_wastage": ["yarn wastage"],
            "value_loss_interest": ["value loss", "interest etc"],
            "payment_term": ["payment term"],
            "commission_cd": ["commission & cd"],
            "other_cost_if_any": ["other cost if any"],
            "extra_remarks_if_any": ["extra remarks if any"],
        }
        output: dict[str, Any] = {}
        for key, labels in row_specs.items():
            anchor = self._find_token_by_text(region_tokens, labels)
            if not anchor:
                continue
            if key == "payment_term":
                output["payment_term"] = self._token_text_to_right(region_tokens, anchor, 400)
                continue
            if key == "extra_remarks_if_any":
                output["extra_remarks_if_any"] = self._token_text_to_right(region_tokens, anchor, 650)
                continue
            row_tokens = [t for t in region_tokens if abs(t.cy - anchor.cy) <= 18 and t.cx > 760]
            rate = self._token_number_near(row_tokens, 822)
            cost = self._token_number_near(row_tokens, 1110)
            if key == "sizing_per_kg":
                output["sizing_per_kg_rate"] = rate
                output["sizing_per_kg_cost"] = cost
            elif key == "weaving_charges":
                output["weaving_charges_rate"] = rate
                output["weaving_charges_cost"] = cost
            elif key == "freight":
                output["freight_rate"] = rate
                output["freight_cost"] = cost
            elif key == "butta_cutting":
                output["butta_cutting_rate"] = rate
                output["butta_cutting_cost"] = cost
            elif key == "yarn_wastage":
                output["yarn_wastage_rate"] = rate
                output["yarn_wastage_cost"] = cost
            elif key == "value_loss_interest":
                output["value_loss_interest_rate"] = rate
                output["value_loss_interest_cost"] = cost
            elif key == "commission_cd":
                output["commission_cd_rate"] = rate
                output["commission_cd_cost"] = cost
            elif key == "other_cost_if_any":
                output["other_cost_if_any_rate"] = rate
        total_anchor = self._find_token_by_text(region_tokens, ["total"])
        if total_anchor:
            total_row = [t for t in region_tokens if abs(t.cy - total_anchor.cy) <= 18 and t.cx > 1000]
            output["particulars_total_cost"] = self._token_number_near(total_row, 1110)
        return output

    def _parse_price_panel(self, tokens: list[OcrToken]) -> dict[str, Any]:
        region_tokens = self._tokens_in_region(tokens, 1400, 780, 1835, 1260)
        output: dict[str, Any] = {}
        mappings = {
            "total_price": ["total price"],
            "target_price": ["target price"],
            "weaving_charge_as_per_tp": ["weaving charge as", "per tp"],
            "order_quantity": ["order quantity"],
            "cover_factor": ["cover factor"],
        }
        for field, labels in mappings.items():
            anchor = self._find_token_by_text(region_tokens, labels)
            output[field] = self._token_number_to_right(region_tokens, anchor, 300) if anchor else None
        yarn_anchor = self._find_token_by_text(region_tokens, ["yarn requirement"])
        if yarn_anchor:
            yarn_tokens = [t for t in region_tokens if t.cy >= yarn_anchor.cy - 10]
            output["yarn_requirement_warp1"] = self._token_number_for_label(yarn_tokens, "warp1", 300)
            output["yarn_requirement_weft1"] = self._token_number_for_label(yarn_tokens, "weft1", 300)
            output["yarn_requirement_total"] = self._token_number_for_label(yarn_tokens, "total", 300)
        return output

    def _tokens_in_region(self, tokens: list[OcrToken], x1: float, y1: float, x2: float, y2: float) -> list[OcrToken]:
        return [t for t in tokens if not (t.x2 < x1 or t.x1 > x2 or t.y2 < y1 or t.y1 > y2)]

    def _normalize_text(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _find_token_by_text(self, tokens: list[OcrToken], needles: list[str]) -> OcrToken | None:
        for token in tokens:
            normalized = self._normalize_text(token.text)
            if all(part in normalized for part in [self._normalize_text(n) for n in needles]):
                return token
        for token in tokens:
            normalized = self._normalize_text(token.text)
            for needle in needles:
                if self._normalize_text(needle) in normalized:
                    return token
        return None

    def _token_number_near(self, tokens: list[OcrToken], target_x: float, max_distance: float = 70) -> float | None:
        numeric = []
        for token in tokens:
            number = self._extract_number(token.text)
            if number is not None:
                numeric.append((abs(token.cx - target_x), token, number))
        numeric = [item for item in numeric if item[0] <= max_distance]
        if not numeric:
            return None
        numeric.sort(key=lambda item: item[0])
        return numeric[0][2]

    def _token_text_near(self, tokens: list[OcrToken], target_x: float, max_distance: float = 70) -> str:
        candidates = [(abs(token.cx - target_x), token.text) for token in tokens if abs(token.cx - target_x) <= max_distance]
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _token_number_to_right(self, tokens: list[OcrToken], anchor: OcrToken | None, max_dx: float) -> float | None:
        if not anchor:
            return None
        row_tokens = [t for t in tokens if abs(t.cy - anchor.cy) <= 22 and anchor.x2 < t.x1 <= anchor.x2 + max_dx]
        numeric = [(t.x1, self._extract_number(t.text)) for t in row_tokens]
        numeric = [item for item in numeric if item[1] is not None]
        return numeric[0][1] if numeric else None

    def _token_text_to_right(self, tokens: list[OcrToken], anchor: OcrToken | None, max_dx: float) -> str:
        if not anchor:
            return ""
        row_tokens = [t for t in tokens if abs(t.cy - anchor.cy) <= 22 and anchor.x2 < t.x1 <= anchor.x2 + max_dx]
        row_tokens.sort(key=lambda t: t.x1)
        return " ".join(t.text for t in row_tokens).strip()

    def _token_number_for_label(self, tokens: list[OcrToken], label: str, max_dx: float) -> float | None:
        anchor = self._find_token_by_text(tokens, [label])
        return self._token_number_to_right(tokens, anchor, max_dx)

    def _recompute_issues(self, data: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for field_name, field_cfg in self.template["fields"].items():
            value = data.get(field_name)
            if field_cfg["type"] == "checkbox":
                continue
            if field_cfg.get("required") and (value is None or value == ""):
                issues.append(f"{field_name}: missing required value")
            if field_cfg["type"] == "number" and field_cfg.get("required") and value is None:
                issues.append(f"{field_name}: numeric parse failed")
        return issues

    def _read_field_text(self, tokens: list[OcrToken], bbox: dict[str, float]) -> tuple[str, float]:
        matching = [
            token for token in tokens
            if bbox["x1"] <= token.cx <= bbox["x2"] and bbox["y1"] <= token.cy <= bbox["y2"]
        ]
        if not matching:
            return "", 0.0
        matching.sort(key=lambda token: (round(token.cy / 8), token.cx))
        text = " ".join(token.text for token in matching).strip()
        confidence = float(np.mean([token.confidence for token in matching]))
        return text, confidence

    def _crop_relative(self, image: np.ndarray, bbox_pct: list[float]) -> tuple[np.ndarray, dict[str, float]]:
        height, width = image.shape[:2]
        x1 = max(0, min(width, int(width * bbox_pct[0])))
        y1 = max(0, min(height, int(height * bbox_pct[1])))
        x2 = max(0, min(width, int(width * bbox_pct[2])))
        y2 = max(0, min(height, int(height * bbox_pct[3])))
        if x2 <= x1:
            x2 = min(width, x1 + 1)
        if y2 <= y1:
            y2 = min(height, y1 + 1)
        return image[y1:y2, x1:x2], {"x1": x1, "y1": y1, "x2": x2, "y2": y2}

    def _detect_checkbox(self, crop: np.ndarray) -> tuple[bool, float]:
        if crop.size == 0:
            return False, 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)
        ratio = cv2.countNonZero(thresh) / max(thresh.size, 1)
        return ratio > 0.08, min(1.0, max(0.5, ratio * 4))

    def _run_ocr(self, crop: np.ndarray) -> tuple[str, float]:
        if self.ocr is None:
            return "", 0.0
        if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0:
            return "", 0.0

        try:
            result = self.ocr.ocr(crop, cls=False)
        except TypeError:
            result = self.ocr.ocr(crop)

        texts: list[str] = []
        scores: list[float] = []
        lines = result[0] if result and result[0] else []
        for line in lines:
            if not line or len(line) < 2:
                continue
            text = line[1][0] if len(line[1]) > 0 else ""
            score = float(line[1][1]) if len(line[1]) > 1 else 0.0
            if text and text.strip():
                texts.append(text.strip())
                scores.append(score)

        return " ".join(texts).strip(), float(np.mean(scores)) if scores else 0.0

    def _normalize_value(self, field_name: str, raw_text: str, field_cfg: dict[str, Any]) -> tuple[Any, list[str]]:
        issues: list[str] = []
        text = re.sub(r"\s+", " ", raw_text.replace("\n", " ")).strip()
        if field_name in NUMERIC_FIELDS or field_cfg["type"] == "number":
            if not text:
                if field_cfg.get("required"):
                    issues.append("missing required value")
                return None, issues
            number = self._extract_number(text)
            if number is None:
                issues.append("numeric parse failed")
                return None, issues
            return number, issues

        if field_cfg.get("required") and not text:
            issues.append("missing required value")
        return text, issues

    def _extract_number(self, text: str) -> float | None:
        match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
        return float(match.group()) if match else None

    def _cross_validate(self, data: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        total = data.get("yarn_requirement_total")
        warp = data.get("yarn_requirement_warp1")
        weft = data.get("yarn_requirement_weft1")
        if all(isinstance(value, (float, int)) for value in [total, warp, weft]) and abs(total - (warp + weft)) > 2:
            issues.append("yarn requirement total does not match warp/weft sum")
        return issues
