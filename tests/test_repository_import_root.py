from pathlib import Path

import commodity


def test_repository_tests_import_current_checkout_source() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    package_file = Path(commodity.__file__).resolve()
    expected_source_root = (repository_root / "src").resolve()

    assert package_file.is_relative_to(expected_source_root), (
        "pytest imported commodity outside the checkout under test: "
        f"{package_file}"
    )
