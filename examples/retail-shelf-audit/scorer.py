"""Ground-truth scorer for the retail shelf audit skill.

SkillSmith copies this file into the generated skill as ``evals/scorer.py`` and
calls ``score(output, ground_truth)`` for every positive evaluation case. Each
returned metric is a float in [0, 1]; the task score is their mean.

Ground truth counts front-row facings per shelf (shelf 1 is the top shelf).
Stacked or back-row units are not extra facings, and items that are not on the
shelf (for example inside a restocking tote) must not be counted. Every count is
an inclusive ``[low, high]`` range so partially occluded cells can be annotated
honestly instead of guessed.
"""
from __future__ import annotations

import re
from typing import Any

# Classes are identified by their dominant package colour first, then by the
# package type, in English and Chinese.
CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "red_can": ("red", "红", "can", "罐"),
    "blue_bottle": ("blue", "蓝", "bottle", "瓶", "water", "水"),
    "green_box": ("green", "绿", "box", "盒", "carton"),
    "yellow_pouch": ("yellow", "黄", "pouch", "bag", "袋", "chip", "薯片", "snack"),
}
COUNT_KEYS = ("facings", "facing_count", "visible_facings", "count", "quantity", "排面", "数量")
SHELF_KEYS = ("shelf", "shelf_level", "shelf_index", "row", "层", "货架层")
POSITIONS = {
    "left": ("left", "左"),
    "center": ("center", "centre", "middle", "中"),
    "right": ("right", "右"),
}
OCCLUSION_WORDS = ("occlu", "block", "obstruct", "hidden", "tote", "crate", "bin", "遮挡", "挡住", "周转箱", "箱")


def _mentions(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(rf"\b{re.escape(word)}", text) is not None
    return word in text


def classify(text: str) -> str | None:
    lowered = text.lower()
    for name, words in CLASS_KEYWORDS.items():
        if any(_mentions(lowered, word) for word in words[:2]):
            return name
    for name, words in CLASS_KEYWORDS.items():
        if any(_mentions(lowered, word) for word in words[2:]):
            return name
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        return int(match.group()) if match else None
    return None


def _first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item:
            return item[key]
    return None


def _position(value: Any) -> str | None:
    text = str(value or "").lower()
    for name, words in POSITIONS.items():
        if any(word in text for word in words):
            return name
    return None


def predicted_cells(output: dict[str, Any]) -> dict[tuple[int, str], int]:
    cells: dict[tuple[int, str], int] = {}
    items = output.get("sku_facings")
    if not isinstance(items, list):
        return cells
    for item in items:
        if not isinstance(item, dict):
            continue
        shelf = _int(_first(item, SHELF_KEYS))
        count = _int(_first(item, COUNT_KEYS))
        label = " ".join(str(v) for k, v in item.items() if isinstance(v, str))
        sku = classify(label)
        if shelf is None or count is None or sku is None:
            continue
        cells[(shelf, sku)] = cells.get((shelf, sku), 0) + count
    return cells


def facing_accuracy(output: dict[str, Any], truth: dict[str, Any]) -> float:
    expected: dict[tuple[int, str], tuple[int, int]] = {}
    for shelf, row in truth["facings"].items():
        for sku, bounds in row.items():
            expected[(int(shelf), sku)] = (bounds[0], bounds[1])
    predicted = predicted_cells(output)
    scores = []
    for cell in expected.keys() | predicted.keys():
        low, high = expected.get(cell, (0, 0))
        value = predicted.get(cell, 0)
        if low <= value <= high:
            scores.append(1.0)
            continue
        distance = low - value if value < low else value - high
        scores.append(max(0.0, 1.0 - distance / max(high, 1)))
    return sum(scores) / len(scores) if scores else 0.0


def gap_f1(output: dict[str, Any], truth: dict[str, Any]) -> float:
    expected = [(int(gap["shelf"]), set(gap["positions"])) for gap in truth["gaps"]]
    items = output.get("empty_gaps")
    predicted = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                predicted.append((_int(_first(item, SHELF_KEYS)), _position(item.get("position") or item.get("location"))))
    if not expected and not predicted:
        return 1.0
    unmatched = list(expected)
    hits = 0
    for shelf, position in predicted:
        for index, (gap_shelf, allowed) in enumerate(unmatched):
            if shelf == gap_shelf and (position is None or position in allowed):
                hits += 1
                del unmatched[index]
                break
    if not hits:
        return 0.0
    precision = hits / len(predicted)
    recall = hits / len(expected)
    return 2 * precision * recall / (precision + recall)


def occlusion_reported(output: dict[str, Any]) -> float:
    text = f"{output.get('uncertainties', '')} {output.get('image_quality', '')}".lower()
    return 1.0 if any(word in text for word in OCCLUSION_WORDS) else 0.0


def score(output: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, float]:
    metrics = {
        "facing_accuracy": facing_accuracy(output, ground_truth),
        "gap_f1": gap_f1(output, ground_truth),
    }
    if ground_truth.get("occluded_shelves"):
        metrics["occlusion_reported"] = occlusion_reported(output)
    return metrics
