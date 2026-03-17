from pathlib import Path
import json


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "domestic_costing_template.json"


def load_template() -> dict:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)
