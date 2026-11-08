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


@pytest.fixture(scope="session")
def election_day_site(tmp_path_factory):
    """The site as built on Election Day, November 3, 2026."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DIST_DIR", tmp_path_factory.mktemp("eday") / "dist")
        yield build.build(date(2026, 11, 3))


@pytest.fixture(scope="session")
def analysis_site(tmp_path_factory):
    """The site a week after the midterms, once the first written analysis pieces are published."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "DIST_DIR", tmp_path_factory.mktemp("analysis") / "dist")
        yield build.build(date(2026, 11, 9))
