from __future__ import annotations

from importlib.resources import as_file

from uri_control import CapabilityRegistry

import urimail


def test_manifest_loads():
    with as_file(urimail.manifest_path()) as path:
        registry = CapabilityRegistry.from_manifest_files([path])
    assert registry.manifests[0].scheme == "urimail"
    assert len(registry.routes) == 5


def test_manifest_matches_routes():
    from urisysedge.runtime import Runtime

    rt = Runtime(config={"mail": {"driver": "mock"}})
    urimail.register(rt)
    assert len(rt.routes) == 5
