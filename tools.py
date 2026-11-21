"""Tool registry and the mail tools.

Every tool call goes through ToolRegistry.execute(). That single choke point is
where the secure tool-call layer (permission scopes, confirmation, verification
and logging hooks) will be attached.
"""

import json
from dataclasses import dataclass
from typing import Callable

from mail_store import Mailbox


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema of the arguments
    func: Callable[..., object]

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
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> str:
        """Run a tool and return its result as a JSON string for the model.

        Failures are returned as {"error": ...} so the model can recover.
        """
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool '{name}'"}, ensure_ascii=False)
        try:
            result = tool.func(**arguments)
        except Exception as e:  # report any tool failure back to the model
            return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
        return json.dumps(result, ensure_ascii=False)


def _params(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


def _string(description: str) -> dict:
    return {"type": "string", "description": description}


def build_mail_tools(mailbox: Mailbox) -> ToolRegistry:
    registry = ToolRegistry()
    email_id = _string("Email id as returned by list_inbox or search_emails, e.g. 'm1'")

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
                "to": _string("Recipient email address"),
                "subject": _string("Subject line"),
                "body": _string("Email body"),
            },
            ["to", "subject", "body"],
        ),
        mailbox.send,
    ))
    registry.register(Tool(
        "forward_email",
        "Forward an existing inbox email to another address.",
        _params({"email_id": email_id, "to": _string("Recipient email address")}, ["email_id", "to"]),
        mailbox.forward,
    ))
    registry.register(Tool(
        "delete_email",
        "Delete an email from the inbox.",
        _params({"email_id": email_id}, ["email_id"]),
        mailbox.delete,
    ))
    return registry
