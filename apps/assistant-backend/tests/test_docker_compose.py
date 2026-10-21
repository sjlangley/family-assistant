"""Tests for the repo-root docker-compose.yml backend service."""

from pathlib import Path

import yaml

COMPOSE_FILE = Path(__file__).resolve().parents[3] / 'docker-compose.yml'


def load_backend() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())['services']['backend']


def test_backend_sets_llm_max_tokens():
    assert 'LLM_MAX_TOKENS' in load_backend()['environment']


def test_backend_depends_on_chroma():
    assert 'chroma' in load_backend()['depends_on']
