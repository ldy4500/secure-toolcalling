"""Tool registry and execution controls for the synthetic mailbox."""

import json
import re
from dataclasses import dataclass
from typing import Callable

from mail_store import Mailbox


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema of the arguments
    func: Callable[..., object]
    requires_confirmation: bool = False
    preview: Callable[[dict], dict] | None = None

    # 모델에 제공할 도구 이름, 설명, 인자 스키마를 구성한다.
    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    # 도구 목록과 요청의 읽기 전용 설정, 승인 콜백을 초기화한다.
    def __init__(
        self, *, read_only: bool = True,
        confirm: Callable[[str, dict], bool] | None = None,
    ):
        self._tools: dict[str, Tool] = {}
        self._read_only = read_only
        self._confirm = confirm

    # 이름으로 도구를 조회할 수 있도록 레지스트리에 등록한다.
    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    # 현재 권한 범위에서 모델에 제공할 도구 명세를 반환한다.
    def schemas(self) -> list[dict]:
        return [
            tool.schema() for tool in self._tools.values()
            if not (self._read_only and tool.requires_confirmation)
        ]

    # 인자와 권한을 검사하고 필요한 승인을 받은 뒤 도구를 실행한다.
    def execute(self, name: str, arguments: dict) -> str:
        """Run a tool and return its result as a JSON string for the model.

        Failures are returned as {"error": ...} so the model can recover.
        """
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool '{name}'"}, ensure_ascii=False)
        if not isinstance(arguments, dict):
            return json.dumps({"error": "invalid_arguments", "message": "Expected an object"})

        arguments = arguments.copy()
        properties = tool.parameters["properties"]
        missing = [field for field in tool.parameters["required"] if field not in arguments]
        if missing:
            return json.dumps({"error": "invalid_arguments", "missing": missing})
        for field, value in arguments.items():
            if field not in properties:
                return json.dumps({"error": "invalid_arguments", "message": "Unexpected field"})
            if not isinstance(value, str):
                return json.dumps({"error": "invalid_arguments", "field": field, "message": "Expected a string"})
            pattern = properties[field].get("pattern")
            if pattern and re.search(pattern, value) is None:
                return json.dumps({"error": "invalid_arguments", "field": field, "message": "Expected a nonblank string"})

        if self._read_only and tool.requires_confirmation:
            return json.dumps({"error": "read_only"})

        try:
            if tool.requires_confirmation:
                if self._confirm is None:
                    return json.dumps({"error": "confirmation_required"})
                preview = tool.preview(arguments) if tool.preview else arguments.copy()
                try:
                    approved = self._confirm(name, preview)
                except (EOFError, KeyboardInterrupt):
                    approved = False
                if approved is not True:
                    return json.dumps({"error": "confirmation_denied"})
            result = tool.func(**arguments)
        except Exception as e:  # report any tool failure back to the model
            return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)


# 필수 인자와 허용 필드를 가진 객체 스키마를 만든다.
def _params(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object", "properties": properties, "required": required,
        "additionalProperties": False,
    }


# 문자열 인자의 스키마를 만들고 필요하면 공백뿐인 값을 제한한다.
def _string(description: str, *, nonblank: bool = False) -> dict:
    schema = {"type": "string", "description": description}
    if nonblank:
        schema["pattern"] = r"\S"
    return schema


# 모의 메일함에 연결된 조회·변경 도구를 등록한다.
def build_mail_tools(
    mailbox: Mailbox, *, read_only: bool = True,
    confirm: Callable[[str, dict], bool] | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(read_only=read_only, confirm=confirm)
    email_id = _string("Email id as returned by list_inbox or search_emails, e.g. 'm1'", nonblank=True)
    recipient = _string("Recipient email address", nonblank=True)

    # 전달하거나 삭제할 원본 메일의 승인 화면에 필요한 정보를 준비한다.
    def existing_mail_preview(arguments: dict) -> dict:
        original = mailbox.read(arguments["email_id"])
        preview = {**arguments, "from": original["from"], "subject": original["subject"]}
        if "to" in arguments:
            preview["original_body_to_be_forwarded"] = original["body"]
        return preview

    registry.register(Tool(
        "list_inbox",
        "List every email in the inbox (id, sender, subject, date). Does not return bodies.",
        _params({}, []),
        mailbox.list_inbox,
    ))
    registry.register(Tool(
        "search_emails",
        "Search the inbox by a keyword matched against sender, subject and body.",
        _params({"query": _string("Keyword to search for")}, ["query"]),
        mailbox.search,
    ))
    registry.register(Tool(
        "read_email",
        "Read the full content of one email.",
        _params({"email_id": email_id}, ["email_id"]),
        mailbox.read,
    ))
    registry.register(Tool(
        "send_email",
        "Send a new email from the user's account.",
        _params(
            {
                "to": recipient,
                "subject": _string("Subject line"),
                "body": _string("Email body"),
            },
            ["to", "subject", "body"],
        ),
        mailbox.send,
        requires_confirmation=True,
    ))
    registry.register(Tool(
        "forward_email",
        "Forward an existing inbox email to another address.",
        _params({"email_id": email_id, "to": recipient}, ["email_id", "to"]),
        mailbox.forward,
        requires_confirmation=True,
        preview=existing_mail_preview,
    ))
    registry.register(Tool(
        "delete_email",
        "Delete an email from the inbox.",
        _params({"email_id": email_id}, ["email_id"]),
        mailbox.delete,
        requires_confirmation=True,
        preview=existing_mail_preview,
    ))
    return registry
