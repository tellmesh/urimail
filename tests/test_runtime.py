from __future__ import annotations

from urisysedge.runtime import Runtime

import urimail


def test_status_mock():
    rt = Runtime(config={"mail": {"driver": "mock"}})
    urimail.register(rt)
    res = rt.call("urimail://local/query/status", {}, {"params": {"account": "local"}})
    assert res["ok"]
    assert res["result"]["driver"] == "mock"


def test_compose_and_send_mock():
    rt = Runtime(config={"mail": {"driver": "mock"}})
    urimail.register(rt)
    compose = rt.call(
        "urimail://local/message/command/compose",
        {"to": "user@example.com", "subject": "Hi", "body": "Test"},
        {"approved": True, "params": {"account": "local"}},
    )
    assert compose["ok"]
    sent = rt.call(
        "urimail://local/message/command/send",
        {},
        {"approved": True, "params": {"account": "local"}},
    )
    assert sent["ok"]
    assert sent["result"]["sent"] is True
