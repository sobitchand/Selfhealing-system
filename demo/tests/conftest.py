"""
pytest integration (integration level 3).

    pytest tests/                # stock Selenium -- tests fail on locator rot
    pytest tests/ --self-heal    # same tests, healing layer installed

The flag is the ONLY difference between the two runs; no test file changes.
"""

import os
import sys

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_DEMO_DIR = os.path.dirname(_TESTS_DIR)
for _p in (_DEMO_DIR, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from driver_factory import make_driver  # noqa: E402


def pytest_addoption(parser):
    parser.addoption("--self-heal", action="store_true",
                     help="install the rule-based self-healing layer")
    parser.addoption("--headed", action="store_true",
                     help="run Chrome visibly")


@pytest.fixture(scope="session", autouse=True)
def healing_layer(request):
    if not request.config.getoption("--self-heal"):
        yield None
        return
    import selfheal
    selfheal.install()

    # Golden baseline is recorded from a KNOWN-GOOD build, never from the page
    # under test. BASELINE_URL points at that build (staging, or the app before
    # the refactor); it defaults to the app root.
    baseline_url = os.environ.get("BASELINE_URL", "http://127.0.0.1:8000")
    selfheal.learn_baseline(
        request.getfixturevalue("driver"),
        url=baseline_url,
        force=os.environ.get("RELEARN_BASELINE") == "1",
    )

    yield selfheal
    stats = selfheal.session_stats()
    print(f"\n🩹 self-healing: {stats['heals']} heals, "
          f"{stats['cache_hits']} cached re-uses, "
          f"locators healed: {', '.join(stats['healed_locators']) or 'none'}")
    selfheal.uninstall()


@pytest.fixture(scope="session")
def driver(request):
    drv = make_driver(headed=request.config.getoption("--headed"))
    yield drv
    drv.quit()
