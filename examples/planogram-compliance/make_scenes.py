"""Compose planogram-compliance test scenes with exact ground truth.

Product sprites and the empty-shelf texture are cut from the synthetic
``retail-shelf-audit/shelf-clear.png`` and pasted onto its own shelf frame, so
every facing in a scene is known by construction. The script writes
``scenes/*.png`` and updates each scene's ``ground_truth`` in ``workflow.json``
from ``reference/planogram-bay-A12.json`` and the store policy below.

Development-only dependency: Pillow (``pip install pillow``).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "retail-shelf-audit/shelf-clear.png"

# Crop boxes in the source image.
SPRITES = {
    "BEV-COLA-330": (38, 40, 108, 290),
    "WAT-550": (538, 45, 608, 292),
    "TEA-250": (1022, 75, 1108, 292),
    "CHP-070": (32, 352, 192, 606),
}
HEIGHT_RATIO = {"TEA-250": 0.82}
EMPTY_PATCH = (962, 330, 1235, 612)
BANDS = [(28, 40, 1512, 292), (28, 335, 1512, 607), (28, 662, 1512, 928)]  # shelf 1..3
GAP_UNIT = 70

# Left-to-right contents per shelf; ("gap", n) leaves n * GAP_UNIT px of bare shelf.
SCENES = {
    "within-tolerance": [
        [("BEV-COLA-330", 6), ("WAT-550", 5), ("TEA-250", 5)],
        [("CHP-070", 3), ("BEV-COLA-330", 4), ("TEA-250", 3)],
        [("TEA-250", 4), ("WAT-550", 5), ("CHP-070", 2), ("BEV-COLA-330", 2)],
    ],
    "tea-oos-water-misplaced": [
        [("BEV-COLA-330", 7), ("WAT-550", 7), ("TEA-250", 6)],
        [("CHP-070", 4), ("BEV-COLA-330", 5), ("gap", 3), ("WAT-550", 3)],
        [("TEA-250", 5), ("WAT-550", 6), ("CHP-070", 2), ("BEV-COLA-330", 3)],
    ],
    "cola-low-chips-oos": [
        [("BEV-COLA-330", 3), ("gap", 3), ("WAT-550", 7), ("TEA-250", 6)],
        [("CHP-070", 4), ("BEV-COLA-330", 5), ("TEA-250", 4)],
        [("TEA-250", 5), ("WAT-550", 6), ("gap", 3), ("BEV-COLA-330", 3)],
    ],
    "mixed-deviations": [
        [("BEV-COLA-330", 7), ("WAT-550", 5), ("TEA-250", 4), ("CHP-070", 1)],
        [("CHP-070", 3), ("BEV-COLA-330", 5), ("TEA-250", 2)],
        [("TEA-250", 5), ("WAT-550", 2), ("gap", 3), ("CHP-070", 2), ("BEV-COLA-330", 3)],
    ],
    "fully-compliant": [
        [("BEV-COLA-330", 7), ("WAT-550", 7), ("TEA-250", 6)],
        [("CHP-070", 4), ("BEV-COLA-330", 5), ("TEA-250", 4)],
        [("TEA-250", 5), ("WAT-550", 6), ("CHP-070", 2), ("BEV-COLA-330", 3)],
    ],
    "cola-oos-tea-low": [
        [("BEV-COLA-330", 7), ("WAT-550", 6), ("TEA-250", 6)],
        [("CHP-070", 4), ("gap", 5), ("TEA-250", 4)],
        [("TEA-250", 3), ("gap", 1), ("WAT-550", 6), ("CHP-070", 2), ("BEV-COLA-330", 3)],
    ],
}

# Held out from evals: used only for the post-install replay on a new input.
HELD_OUT = {
    "replay-a12-evening": [
        [("BEV-COLA-330", 4), ("gap", 3), ("WAT-550", 7), ("TEA-250", 5)],
        [("CHP-070", 4), ("BEV-COLA-330", 5), ("TEA-250", 4)],
        [("TEA-250", 5), ("WAT-550", 3), ("gap", 2), ("BEV-COLA-330", 3), ("TEA-250", 1)],
    ],
}


def status_ground_truth(layout: list[list[tuple[str, int]]], planogram: dict) -> dict:
    """Store policy: 0 facings = OOS, below min = LOW, otherwise OK; unplanned SKU on a shelf = MISPLACED."""
    observed: dict[tuple[int, str], int] = {}
    for shelf, row in enumerate(layout, 1):
        for sku, count in row:
            if sku != "gap":
                observed[(shelf, sku)] = observed.get((shelf, sku), 0) + count
    items = []
    for shelf_key, slots in planogram["shelves"].items():
        shelf = int(shelf_key)
        planned = {slot["sku_code"] for slot in slots}
        for slot in slots:
            count = observed.get((shelf, slot["sku_code"]), 0)
            status = "OOS" if count == 0 else "LOW" if count < slot["min_facings"] else "OK"
            items.append({"shelf": shelf, "sku_code": slot["sku_code"], "observed_facings": count, "status": status})
        for (obs_shelf, sku), count in sorted(observed.items()):
            if obs_shelf == shelf and sku not in planned:
                items.append({"shelf": shelf, "sku_code": sku, "observed_facings": count, "status": "MISPLACED"})
    return {"items": items}


def compose(layout: list[list[tuple[str, int]]], source: Image.Image) -> Image.Image:
    image = source.copy()
    patch = source.crop(EMPTY_PATCH)
    sprites = {sku: source.crop(box) for sku, box in SPRITES.items()}
    for (x0, y0, x1, y1), row in zip(BANDS, layout):
        height = y1 - y0
        texture = patch.resize((patch.width, height))
        for x in range(x0, x1, texture.width):
            image.paste(texture.crop((0, 0, min(texture.width, x1 - x), height)), (x, y0))
        x = x0 + 6
        for sku, count in row:
            if sku == "gap":
                x += count * GAP_UNIT
                continue
            sprite = sprites[sku]
            sprite_height = int(height * HEIGHT_RATIO.get(sku, 0.92))
            sprite = sprite.resize((int(sprite.width * sprite_height / sprite.height), sprite_height))
            for _ in range(count):
                image.paste(sprite, (x, y1 - sprite_height - 4))
                x += sprite.width + 3
        if x > x1:
            raise ValueError(f"row overflows the shelf by {x - x1}px: {row}")
    return image


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    planogram = json.loads((HERE / "reference/planogram-bay-A12.json").read_text(encoding="utf-8"))
    workflow_path = HERE / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in workflow["evals"]}
    (HERE / "scenes").mkdir(exist_ok=True)
    notes = []
    for name, layout in SCENES.items():
        path = HERE / "scenes" / f"{name}.png"
        compose(layout, source).save(path, optimize=True)
        cases[name]["ground_truth"] = status_ground_truth(layout, planogram)
        notes.append(f"- `scenes/{name}.png` SHA-256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`")
    workflow_path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    held_out = {}
    for name, layout in HELD_OUT.items():
        path = HERE / "scenes" / f"{name}.png"
        compose(layout, source).save(path, optimize=True)
        held_out[name] = status_ground_truth(layout, planogram)
        notes.append(f"- `scenes/{name}.png` (held out) SHA-256 `{hashlib.sha256(path.read_bytes()).hexdigest()}`")
    (HERE / "scenes/held-out-ground-truth.json").write_text(
        json.dumps(held_out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("\n".join(notes))


if __name__ == "__main__":
    main()
