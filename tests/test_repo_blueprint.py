from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_repository_blueprint_files_exist() -> None:
    expected_paths = [
        ROOT / "agent.md",
        ROOT / "docs" / "product-requirements.md",
        ROOT / "docs" / "system-design.md",
        ROOT / "docs" / "evaluation-design.md",
        ROOT / "docs" / "repo-blueprint.md",
        ROOT / "docs" / "decision-log.md",
        ROOT / "pyproject.toml",
        ROOT / "README.md",
    ]

    missing = [str(path.relative_to(ROOT)) for path in expected_paths if not path.exists()]

    assert not missing, f"Missing expected files: {missing}"


def test_repository_blueprint_directories_exist() -> None:
    expected_dirs = [
        ROOT / "apps" / "cli",
        ROOT / "apps" / "web",
        ROOT / "packages" / "py-core",
        ROOT / "packages" / "py-agents",
        ROOT / "packages" / "py-evals",
        ROOT / "packages" / "ts-shared",
        ROOT / "fixtures",
        ROOT / "examples",
        ROOT / "tests",
    ]

    missing = [str(path.relative_to(ROOT)) for path in expected_dirs if not path.exists()]

    assert not missing, f"Missing expected directories: {missing}"
