"""Synthetic in-memory mailbox. Nothing here touches a real mail service."""

import copy
import json
from datetime import datetime
from pathlib import Path


class MailboxError(Exception):
    pass


class Mailbox:
    def __init__(self, owner: str, inbox: list[dict]):
        self.owner = owner
        self.inbox = copy.deepcopy(inbox)
        self.sent: list[dict] = []
        self.deleted: list[dict] = []

    @classmethod
    def from_file(cls, path: Path) -> "Mailbox":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(owner=data["owner"], inbox=data["inbox"])

    def _find(self, email_id: str) -> dict:
        for email in self.inbox:
            if email["id"] == email_id:
                return email
        raise MailboxError(f"No email with id '{email_id}' in the inbox")

    @staticmethod
    def _summary(email: dict) -> dict:
        return {k: email[k] for k in ("id", "from", "subject", "date")}

    def list_inbox(self) -> list[dict]:
        return [self._summary(e) for e in self.inbox]

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [
            self._summary(e)
            for e in self.inbox
            if q in e["from"].lower() or q in e["subject"].lower() or q in e["body"].lower()
        ]

    def read(self, email_id: str) -> dict:
        return dict(self._find(email_id))

    def send(self, to: str, subject: str, body: str) -> dict:
        message = {
            "id": f"s{len(self.sent) + 1}",
            "from": self.owner,
            "to": to,
            "subject": subject,
            "body": body,
            "date": datetime.now().isoformat(timespec="seconds"),
        }
        self.sent.append(message)
        return {"status": "sent", "id": message["id"], "to": to}

    def forward(self, email_id: str, to: str) -> dict:
        original = self._find(email_id)
        body = (
            f"---------- Forwarded message ----------\n"
            f"From: {original['from']}\nDate: {original['date']}\n"
            f"Subject: {original['subject']}\n\n{original['body']}"
        )
        result = self.send(to, f"Fwd: {original['subject']}", body)
        self.sent[-1]["forwarded_from"] = email_id
        return {**result, "status": "forwarded", "forwarded_from": email_id}

    def delete(self, email_id: str) -> dict:
        email = self._find(email_id)
        self.inbox.remove(email)
        self.deleted.append(email)
        return {"status": "deleted", "id": email_id}
