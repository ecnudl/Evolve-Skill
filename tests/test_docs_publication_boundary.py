"""Product-site publishing must not sweep in research or local-only files."""

from pathlib import Path

import pytest

config_module = pytest.importorskip("mkdocs.config")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def config():
    return config_module.load_config(str(ROOT / "mkdocs.yml"))


@pytest.mark.parametrize(
    "relative_path",
    [
        "current-workflow.md",
        "results-and-lessons.md",
        "future-research-report.md",
        "results/example.json",
        "superpowers/specs/design.md",
        "network.local.md",
        "guide/network.local.md",
        "assets/private.local.json",
        "assets/private.local.svg",
    ],
)
def test_private_and_github_only_documents_excluded(config, relative_path):
    assert config["exclude_docs"].match_file(relative_path)


@pytest.mark.parametrize(
    "relative_path",
    [
        "index.md",
        "contributing.md",
        "review_guidelines.md",
        "guide/configuration.md",
        "reference/cli.md",
        "sleep/README.md",
        "sleep/examples/runner.py",
    ],
)
def test_product_documents_remain_included(config, relative_path):
    assert (ROOT / "docs" / relative_path).is_file()
    assert not config["exclude_docs"].match_file(relative_path)


def test_all_local_navigation_destinations_are_published(config):
    def visit(value):
        if isinstance(value, list):
            for item in value:
                yield from visit(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from visit(item)
        elif isinstance(value, str):
            yield value

    for destination in visit(config["nav"]):
        if destination.startswith(("https://", "http://")):
            continue
        relative_path = destination.split("#", 1)[0]
        assert (ROOT / "docs" / relative_path).is_file()
        assert not config["exclude_docs"].match_file(relative_path)
