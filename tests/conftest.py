"""Pytest configuration and session-level fixtures for GoComet Nova test suite."""

import os
import pytest

from evals.generate_dataset import DATASET_DIR, generate_all


@pytest.fixture(scope="session", autouse=True)
def ensure_eval_dataset():
    """Ensure evaluation dataset exists on fresh clones before test suites execute."""
    if not os.path.exists(DATASET_DIR) or len(os.listdir(DATASET_DIR)) < 12:
        os.makedirs(DATASET_DIR, exist_ok=True)
        generate_all(verify=True)
