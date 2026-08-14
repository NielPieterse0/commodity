import json
from pathlib import Path

import pandas as pd

RECIPE_ROOT = Path(__file__).parents[1] / "config" / "acquisition-recipes"


def _recipe(recipe_id: str) -> dict:
    return json.loads((RECIPE_ROOT / f"{recipe_id}.json").read_text(encoding="utf-8"))


def test_weather_v1_recipe_is_bounded_to_configured_request_shape() -> None:
    recipe = _recipe("commodity-open-meteo-ecmwf-v1")
    assert recipe["request"]["url"] == "https://single-runs-api.open-meteo.com/v1/forecast"
    assert recipe["request"]["query"]["models"] == {"literal": "ecmwf_ifs"}
    assert recipe["request"]["query"]["forecast_days"] == {"literal": "10"}
    assert recipe["request"]["query"]["hourly"] == {
        "literal": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m"
    }
    assert set(recipe["parameters"]) == {"latitude", "longitude", "run"}


def test_nyiso_v1_recipes_cover_exact_required_months() -> None:
    expected_months = pd.date_range("2024-08-01", "2026-08-01", freq="MS")
    actual = sorted(RECIPE_ROOT.glob("commodity-nyiso-isolf-*.json"))
    assert len(actual) == len(expected_months) == 25
    for month, path in zip(expected_months, actual, strict=True):
        ym = month.strftime("%Y%m")
        recipe_id = f"commodity-nyiso-isolf-{ym}"
        recipe = json.loads(path.read_text(encoding="utf-8"))
        assert recipe["recipe_id"] == recipe_id
        assert recipe["parameters"] == {}
        assert recipe["request"]["query"] == {}
        assert recipe["request"]["url"] == (
            f"https://mis.nyiso.com/public/csv/isolf/{ym}01isolf_csv.zip"
        )
