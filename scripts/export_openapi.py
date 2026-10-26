"""Export the live API contract. JSON is also valid YAML (OpenAPI accepts both)."""

import json
from pathlib import Path

from psychohelp.main import app


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "swagger.yaml"
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI exported to {output}")
