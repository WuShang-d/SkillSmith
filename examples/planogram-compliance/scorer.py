"""Ground-truth scorer for the planogram-compliance skill.

Ground truth lists every planned (shelf, sku_code) slot plus every MISPLACED
SKU, with its observed front-row facings and status under the store policy.
Scenes are composed from known sprites, so the ground truth is exact.
"""
from __future__ import annotations

import re
from typing import Any

STATUSES = {"OK", "LOW", "OOS", "MISPLACED"}


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        return int(match.group()) if match else None
    return None


def predicted_items(output: dict[str, Any]) -> dict[tuple[int, str], dict[str, Any]]:
    items = output.get("items")
    predicted: dict[tuple[int, str], dict[str, Any]] = {}
    if not isinstance(items, list):
        return predicted
    for item in items:
        if not isinstance(item, dict):
            continue
        shelf = _int(item.get("shelf"))
        code = str(item.get("sku_code", "")).strip().upper()
        status = str(item.get("status", "")).strip().upper()
        if shelf is None or not code:
            continue
        predicted[(shelf, code)] = {"status": status, "facings": _int(item.get("observed_facings"))}
    return predicted


def score(output: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, float]:
    expected = {(item["shelf"], item["sku_code"]): item for item in ground_truth["items"]}
    predicted = predicted_items(output)

    # Status accuracy over planned slots and true MISPLACED entries; any extra
    # (shelf, sku) the model invents counts against it.
    keys = expected.keys() | predicted.keys()
    status_hits = [
        key in expected and key in predicted and predicted[key]["status"] == expected[key]["status"]
        for key in keys
    ]

    # Deviation detection: the actionable part of the report.
    true_dev = {key for key, item in expected.items() if item["status"] != "OK"}
    pred_dev = {key for key, item in predicted.items() if item["status"] in STATUSES - {"OK"}}
    hits = len(true_dev & pred_dev)
    if not true_dev and not pred_dev:
        deviation_f1 = 1.0
    elif not hits:
        deviation_f1 = 0.0
    else:
        precision, recall = hits / len(pred_dev), hits / len(true_dev)
        deviation_f1 = 2 * precision * recall / (precision + recall)

    facing_hits = [
        key in predicted and predicted[key]["facings"] == item["observed_facings"]
        for key, item in expected.items()
    ]
    return {
        "status_accuracy": sum(status_hits) / len(status_hits) if status_hits else 0.0,
        "deviation_f1": deviation_f1,
        "facing_exact": sum(facing_hits) / len(facing_hits),
    }
