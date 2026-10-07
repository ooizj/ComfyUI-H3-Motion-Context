"""Local, per-execution prompt records for the H3 nodes."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import uuid

import folder_paths
from comfy_execution.utils import get_executing_context

_LOG = logging.getLogger("h3_motion_context")


def new_prompt_log_path(kind):
    name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ_") + uuid.uuid4().hex[:8]
    return Path(folder_paths.get_output_directory()) / "h3_prompt_logs" / f"{name}_{kind}.json"


def prompt_request_log(payload, stage):
    messages = []
    for message in payload["messages"]:
        content = message["content"]
        if isinstance(content, list):
            content = [part if part["type"] == "text" else {"type": part["type"], "omitted": True} for part in content]
        messages.append({"role": message["role"], "content": content})
    return {**payload, "stage": stage, "messages": messages}


def prompt_trace_text(requests, responses):
    sections = []
    for request in requests:
        sections.append(f"AI request: {request['stage']}")
        sections.append(json.dumps({k: v for k, v in request.items() if k not in ("stage", "messages")}, ensure_ascii=False))
        for message in request["messages"]:
            content = message["content"]
            if isinstance(content, list):
                content = "\n".join(part["text"] if part["type"] == "text" else "[image data omitted]" for part in content)
            sections.append(f"{message['role']}:\n{content}")
        for response in responses:
            if response["stage"] == request["stage"]:
                sections.append(f"AI response ({response['finish_reason']}):\n{response['content']}")
    return "\n\n".join(sections)


def write_prompt_log(path, report, text, api_key=""):
    context = get_executing_context()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_id": context.prompt_id if context else None,
        "node_id": context.node_id if context else None,
        **report,
    }
    text = (f"Time: {report['created_at']}\nTask: {report['prompt_id']}\nNode: {report['node_id']}\n"
            f"Operation: {report['operation']}\nStatus: {report['status']}\n\n{text}")
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if api_key.strip():
        text = text.replace(api_key.strip(), "[REDACTED]")
        serialized = serialized.replace(json.dumps(api_key.strip(), ensure_ascii=False)[1:-1], "[REDACTED]")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        path.with_suffix(".txt").write_text(text, encoding="utf-8")
    except OSError as error:
        _LOG.warning("H3 Prompt: could not save log (%s)", error.strerror)
        return None
    _LOG.info("H3 Prompt: %s (%s); log: %s", report["operation"], report["status"], path.with_suffix(".txt"))
    return str(path.with_suffix(".txt"))
