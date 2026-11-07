import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        help="Authorize real Copilot network/account integration tests",
    )
    parser.addoption(
        "--live-login", action="store_true", help="Wait for manual login during live tests"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        skip = pytest.mark.skip(reason="Live Copilot account test; explicitly opt in with --live")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip)
