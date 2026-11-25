"""Every module of the package imports."""

import importlib

import pytest

MODULES = [
    "chole_demo",
    "chole_demo.client",
    "chole_demo.feeds",
    "chole_demo.session_log",
    "chole_demo.client.adapter",
    "chole_demo.feeds.mock",
    "chole_demo.server",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    assert importlib.import_module(name) is not None
