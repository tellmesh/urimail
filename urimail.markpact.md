# UriPack: urimail

Self-contained Markpact — definitions, full source, run config. Unpack & run: `urisys markpact run urimail/urimail.markpact.md --as service` (writes `.markpact/`).

```yaml markpact:pack
apiVersion: urisys.io/v1
kind: UriPack
metadata:
  id: urimail-pack
  version: 1.0.0
  language: python
description: Mail mock/mailpit/smtp automation for urisys-node.
schemes:
- urimail
capabilities:
- id: mail.status
  uri: urimail://{account}/query/status
  kind: query
  operation: mail.status
  handler: python://urimail.handlers:status
  side_effects: false
  approval: not_required
- id: mail.inbox.unread
  uri: urimail://{account}/inbox/query/unread
  kind: query
  operation: mail.inbox.unread
  handler: python://urimail.handlers:inbox_unread
  side_effects: false
  approval: not_required
- id: mail.message.compose
  uri: urimail://{account}/message/command/compose
  kind: command
  operation: mail.message.compose
  handler: python://urimail.handlers:message_compose
  side_effects: true
  approval: required
- id: mail.message.send
  uri: urimail://{account}/message/command/send
  kind: command
  operation: mail.message.send
  handler: python://urimail.handlers:message_send
  side_effects: true
  approval: required
- id: mail.message.publish_post
  uri: urimail://{account}/message/command/publish-post
  kind: command
  operation: mail.message.publish_post
  handler: python://urimail.handlers:message_publish_post
  side_effects: true
  approval: required
policy:
  default: deny_mutations_without_approval
runtime:
  default_environment: mock
  supports:
  - mock
  - local
  - docker
```

```yaml markpact:run
modes:
- pack
- service
- flow
- interface
- adapter
default: service
scheme: urimail
service:
  port: 8790
  wire: POST /uri/call
flow:
  ids: []
adapter:
  wire: POST /uri/call
  events: GET /events
```

```python markpact:module path=urimail/__init__.py
from __future__ import annotations

from importlib.resources import files

from .routes import register

__all__ = ["register", "manifest_path"]


def manifest_path():
    return files(__package__).joinpath("manifest.yaml")
```

```python markpact:module path=urimail/handlers.py
from __future__ import annotations

import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any


def _mail_cfg(context: dict[str, Any]) -> dict[str, Any]:
    return context.get("config", {}).get("mail") or {}


def _driver(context: dict[str, Any]) -> str:
    return str(_mail_cfg(context).get("driver") or os.environ.get("URISYS_MAIL_DRIVER") or "mock")


def _draft_state(context: dict[str, Any]) -> dict[str, Any]:
    account = context.get("params", {}).get("account", "local")
    drafts = context.setdefault("state", {}).setdefault("mail_drafts", {})
    return drafts.setdefault(account, {"to": "", "subject": "", "body": ""})


def _real_allowed(context: dict[str, Any]) -> bool:
    return bool(context.get("allow_real") or os.environ.get("URISYS_ALLOW_REAL") == "1")


def _mailpit_api(context: dict[str, Any]) -> str:
    cfg = _mail_cfg(context)
    return str(cfg.get("mailpit_api") or os.environ.get("URISYS_MAILPIT_API") or "http://127.0.0.1:8025/api/v1")


def _mailpit_messages(context: dict[str, Any]) -> list[dict[str, Any]]:
    url = _mailpit_api(context).rstrip("/") + "/messages"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict) and isinstance(data.get("messages"), list):
        return data["messages"]
    if isinstance(data, list):
        return data
    return []


def status(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del payload
    cfg = _mail_cfg(context)
    return {
        "driver": _driver(context),
        "mailpit_api": _mailpit_api(context),
        "smtp_host": cfg.get("smtp_host") or os.environ.get("URISYS_SMTP_HOST") or "127.0.0.1",
        "smtp_port": int(cfg.get("smtp_port") or os.environ.get("URISYS_SMTP_PORT") or "1025"),
        "supports": ["mock", "mailpit", "smtp"],
    }


def inbox_unread(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    driver = payload.get("driver") or _driver(context)
    limit = int(payload.get("limit") or 20)
    if driver == "mailpit" and _real_allowed(context):
        try:
            messages = _mailpit_messages(context)
            unread = [m for m in messages if not m.get("Read")][:limit]
            return {
                "driver": driver,
                "count": len(unread),
                "messages": [
                    {
                        "id": m.get("ID"),
                        "from": (m.get("From") or {}).get("Address"),
                        "subject": m.get("Subject"),
                        "snippet": m.get("Snippet"),
                    }
                    for m in unread
                ],
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
            return {"ok": False, "error": f"mailpit unread failed: {exc}", "driver": driver}
    sample = [
        {"id": "mock-1", "from": "boss@example.com", "subject": "Weekly report", "snippet": "Please review..."},
        {"id": "mock-2", "from": "team@example.com", "subject": "Standup notes", "snippet": "Action items..."},
    ]
    return {"driver": "mock", "count": len(sample), "messages": sample[:limit]}


def message_compose(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    draft = _draft_state(context)
    draft["to"] = str(payload.get("to") or draft.get("to") or "")
    draft["subject"] = str(payload.get("subject") or payload.get("title") or draft.get("subject") or "")
    draft["body"] = str(payload.get("body") or payload.get("text") or payload.get("summary") or draft.get("body") or "")
    if context.get("dry_run"):
        return {"dry_run": True, "draft": dict(draft)}
    return {"composed": True, "draft": dict(draft)}


def message_send(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    driver = payload.get("driver") or _driver(context)
    draft = _draft_state(context)
    to_addr = str(payload.get("to") or draft.get("to") or "")
    subject = str(payload.get("subject") or draft.get("subject") or "")
    body = str(payload.get("body") or draft.get("body") or "")
    if not to_addr:
        return {"ok": False, "error": "payload.to is required for send-mail"}
    if context.get("dry_run"):
        return {"dry_run": True, "driver": driver, "to": to_addr, "subject": subject, "chars": len(body)}
    if driver in ("mailpit", "smtp") and _real_allowed(context):
        cfg = _mail_cfg(context)
        host = str(cfg.get("smtp_host") or os.environ.get("URISYS_SMTP_HOST") or "127.0.0.1")
        port = int(cfg.get("smtp_port") or os.environ.get("URISYS_SMTP_PORT") or "1025")
        msg = EmailMessage()
        msg["From"] = str(cfg.get("from_addr") or os.environ.get("URISYS_MAIL_FROM") or "urisys@local.test")
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.send_message(msg)
        return {"sent": True, "driver": driver, "to": to_addr, "subject": subject, "via": f"{host}:{port}"}
    return {"sent": True, "driver": "mock", "to": to_addr, "subject": subject, "mock": True}


def message_publish_post(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    platform = str(payload.get("platform") or "linkedin")
    text = str(payload.get("text") or payload.get("body") or "")
    cfg = _mail_cfg(context)
    via = str(payload.get("via") or cfg.get("publish_via") or "mock").lower()
    if context.get("dry_run"):
        return {"dry_run": True, "platform": platform, "chars": len(text), "via": via}
    if via == "browser":
        try:
            from uribrowserdocker.handlers import publish_post as browser_publish_post
        except ModuleNotFoundError as exc:
            raise RuntimeError("publish_via=browser requires pip install uribrowser") from exc
        browser_ctx = dict(context)
        browser_ctx.setdefault("config", {})
        browser_cfg = dict(browser_ctx["config"].get("browser") or {})
        browser_cfg.setdefault("driver", "system-open")
        browser_ctx["config"] = {**browser_ctx["config"], "browser": browser_cfg}
        browser_ctx.setdefault("params", {"session": platform})
        out = browser_publish_post({"platform": platform, "text": text, **payload}, browser_ctx)
        return {"platform": platform, "via": "browser", **out}
    return {"published": True, "platform": platform, "mock": True, "chars": len(text)}
```

```python markpact:module path=urimail/routes.py
from __future__ import annotations

from importlib.resources import files

from urisysedge.manifest import register_manifest_file


def register(runtime):
    register_manifest_file(runtime, files(__package__).joinpath("manifest.yaml"))
```

```markdown markpact:docs
# urimail


## AI Cost Tracking

![PyPI](https://img.shields.io/badge/pypi-costs-blue) ![Version](https://img.shields.io/badge/version-0.1.2-blue) ![Python](https://img.shields.io/badge/python-3.9+-blue) ![License](https://img.shields.io/badge/license-Apache--2.0-green)
![AI Cost](https://img.shields.io/badge/AI%20Cost-$0.15-orange) ![Human Time](https://img.shields.io/badge/Human%20Time-1.0h-blue) ![Model](https://img.shields.io/badge/Model-openrouter%2Fqwen%2Fqwen3--coder--next-lightgrey)

- 🤖 **LLM usage:** $0.1500 (1 commits)
- 👤 **Human dev:** ~$100 (1.0h @ $100/h, 30min dedup)

Generated on 2026-06-17 using [openrouter/qwen/qwen3-coder-next](https://openrouter.ai/qwen/qwen3-coder-next)

---



urimail:// URI capability pack for urisys-node.

Licensed under Apache-2.0.
```

