"""Synthetic in-memory mailbox. Nothing here touches a real mail service."""

import copy
import json
from datetime import datetime
from pathlib import Path


class MailboxError(Exception):
    pass


class Mailbox:
    # 초기 받은메일을 복사하고 모의 발송·삭제 기록을 준비한다.
    def __init__(self, owner: str, inbox: list[dict]):
        self.owner = owner
        self.inbox = copy.deepcopy(inbox)
        self.sent: list[dict] = []
        self.deleted: list[dict] = []

    # JSON 파일에서 사용자와 받은메일을 읽어 모의 메일함을 만든다.
    @classmethod
    def from_file(cls, path: Path) -> "Mailbox":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(owner=data["owner"], inbox=data["inbox"])

    # 메일 ID로 받은메일을 찾고 없으면 오류를 발생시킨다.
    def _find(self, email_id: str) -> dict:
        for email in self.inbox:
            if email["id"] == email_id:
                return email
        raise MailboxError(f"No email with id '{email_id}' in the inbox")

    # 본문을 제외한 메일의 기본 정보를 반환한다.
    @staticmethod
    def _summary(email: dict) -> dict:
        return {k: email[k] for k in ("id", "from", "subject", "date")}

    # 받은메일의 기본 정보 목록을 반환한다.
    def list_inbox(self) -> list[dict]:
        return [self._summary(e) for e in self.inbox]

    # 보낸 사람, 제목, 본문에서 키워드를 검색한다.
    def search(self, query: str) -> list[dict]:
        q = query.lower()
        return [
            self._summary(e)
            for e in self.inbox
            if q in e["from"].lower() or q in e["subject"].lower() or q in e["body"].lower()
        ]

    # 지정한 메일의 전체 정보를 복사해 반환한다.
    def read(self, email_id: str) -> dict:
        return dict(self._find(email_id))

    # 새 메일을 모의 보낸메일함에 기록한다.
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

    # 원본 메일을 인용해 모의 전달 내역을 기록한다.
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

    # 메일을 받은메일함에서 제거하고 삭제 기록에 남긴다.
    def delete(self, email_id: str) -> dict:
        email = self._find(email_id)
        self.inbox.remove(email)
        self.deleted.append(email)
        return {"status": "deleted", "id": email_id}
