import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PROGRAMMES = ROOT / "research" / "programmes"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_name: str, path: Path) -> dict:
    schema = load_json(ROOT / "contracts" / schema_name)
    value = load_json(path)
    errors = list(Draft202012Validator(schema).iter_errors(value))
    assert not errors, f"{path}: {errors[0].message if errors else ''}"
    return value


def test_programmes_own_numbered_research_line_hierarchy() -> None:
    assert not (ROOT / "research" / "programme").exists()
    assert not (ROOT / "research" / "experiments").exists()
    programme_dirs = sorted(path for path in PROGRAMMES.iterdir() if path.is_dir())
    assert programme_dirs
    for programme_dir in programme_dirs:
        programme = validate("programme.schema.json", programme_dir / "programme.json")
        assert programme_dir.name == programme["programme_id"]
        assert programme["line_refs"]
        evidence = load_json(programme_dir / "evidence-map.json")
        assert evidence["programme_id"] == programme["programme_id"]
        assert evidence["research_line_refs"] == programme["line_refs"]
        for ref in programme["line_refs"]:
            line_path = ROOT / ref["path"]
            line = validate("research_line.schema.json", line_path)
            assert line_path.parent.name == line["research_line_id"]
            assert line["research_line_id"] == ref["research_line_id"]
            assert line["programme_id"] == programme["programme_id"]
            experiments_dir = line_path.parent / "experiments"
            assert experiments_dir.is_dir()
            for experiment_ref in line["experiment_refs"]:
                experiment_dir = ROOT / experiment_ref["path"]
                assert experiment_dir.parent == experiments_dir
                legacy_path = experiment_dir / "legacy-record.json"
                prereg_path = experiment_dir / "prereg.json"
                assert legacy_path.is_file() != prereg_path.is_file()
                if legacy_path.is_file():
                    legacy = validate("legacy_experiment_record.schema.json", legacy_path)
                    assert legacy["programme_id"] == programme["programme_id"]
                    assert legacy["research_line_id"] == line["research_line_id"]
                    assert legacy["experiment_id"] == experiment_ref["experiment_id"]
                    continue
                prereg = load_json(prereg_path)
                record = load_json(experiment_dir / "record.json")
                assert prereg["programme_id"] == programme["programme_id"]
                assert prereg["research_line_id"] == line["research_line_id"]
                assert prereg["experiment_id"] == experiment_ref["experiment_id"]
                assert record["programme_id"] == programme["programme_id"]
                assert record["research_line_id"] == line["research_line_id"]
                assert record["experiment_id"] == experiment_ref["experiment_id"]


def test_legacy_programme_history_is_harvested_not_empty() -> None:
    programme_dir = PROGRAMMES / "001-commodity-natural-gas"
    programme = load_json(programme_dir / "programme.json")
    experiment_refs = []
    for line_ref in programme["line_refs"]:
        line = load_json(ROOT / line_ref["path"])
        experiment_refs.extend(line["experiment_refs"])
        assert not (ROOT / line_ref["path"]).parent.joinpath("evidence").exists()
    assert len(experiment_refs) >= 19
    assert not (programme_dir / "lines" / "006-post-v2-portfolio-compression").exists()
    assert not (programme_dir / "lines" / "007-methodology-hardening").exists()
    assert len(load_json(programme_dir / "decisions.json")["decisions"]) >= 20
    assert load_json(programme_dir / "backlog.json")["items"]
    assert len(load_json(programme_dir / "inference-ledger.json")["entries"]) >= 13
