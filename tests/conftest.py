from datetime import date

import pytest

from pipeline import build, config

AS_OF = date(2026, 10, 31)


@pytest.fixture(scope="session")
def site(tmp_path_factory):
    """The full site, built once per test run into a temporary dist/."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DIST_DIR", tmp_path_factory.mktemp("site") / "dist")
        yield build.build(AS_OF)
