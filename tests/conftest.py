from __future__ import annotations

from pathlib import Path

import pytest

from storycanon.db import Canon


@pytest.fixture
def project(tmp_path: Path) -> Canon:
    canon = Canon(tmp_path)
    canon.init_project(
        premise="A disgraced archivist discovers the empire's founding records were forged.",
        title="The Forged Archive",
    )
    return canon
