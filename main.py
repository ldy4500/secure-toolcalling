"""CLI for the synthetic mail agent.

    python main.py "받은편지함 목록 보여줘"     one task, then exit
    python main.py                              interactive mode
"""

import argparse
import json
import sys
import unicodedata

import config
from agent import ToolCallRecord, run_agent
from llm import ChatClient, LLMError
from mail_store import Mailbox
from tools import build_mail_tools


# 도구에 전달한 인자와 실행 결과의 일부를 출력한다.
def print_tool_call(record: ToolCallRecord) -> None:
    args = json.dumps(record.arguments, ensure_ascii=False)
    result = record.result if len(record.result) <= 300 else record.result[:300] + "..."
    print(f"  [tool] {record.name}({args})")
    print(f"         -> {result}")


# 모의 메일함에 기록된 발송·전달·삭제 내역을 출력한다.
def print_mailbox_changes(mailbox: Mailbox) -> None:
    print("\n=== Mailbox changes ===")
    if not mailbox.sent and not mailbox.deleted:
        print("(none)")
    for m in mailbox.sent:
        kind = "FORWARDED" if "forwarded_from" in m else "SENT"
        print(f"{kind} to {m['to']} | {m['subject']}")
    for m in mailbox.deleted:
        print(f"DELETED {m['id']} | {m['subject']}")


# 변경 내용을 보여주고 대화형 터미널에서 명시적인 승인을 받는다.
def confirm_tool(name: str, preview: dict) -> bool:
    if not sys.stdin.isatty():
        return False
    print(f"\nConfirm mailbox change: {name}")
    details = json.dumps(preview, ensure_ascii=False, indent=2)
    print("".join(
        ascii(char)[1:-1] if char != "\n" and unicodedata.category(char).startswith("C") else char
        for char in details
    ))
    return input("Execute this operation? [y/N] ").strip().lower() == "y"


# 요청의 권한 범위로 도구를 구성하고 에이전트를 한 번 실행한다.
def run_task(client: ChatClient, mailbox: Mailbox, task: str, *, read_only: bool = True) -> None:
    registry = build_mail_tools(mailbox, read_only=read_only, confirm=confirm_tool)
    result = run_agent(client, registry, mailbox.owner, task, on_tool_call=print_tool_call)
    print(f"\nAgent: {result.final_text}")


# 명령줄 인자를 읽고 단일 요청 또는 대화형 모드를 실행한다.
def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Mail agent (synthetic mailbox, read-only by default)")
    parser.add_argument("task", nargs="?", help="Task for the agent. Omit for interactive mode.")
    parser.add_argument("--seed", default=str(config.SEED_MAILBOX), help="Seed mailbox JSON file")
    parser.add_argument(
        "--allow-write", action="store_true",
        help="Allow this task to request confirmation for mailbox changes",
    )
    args = parser.parse_args()
    if args.allow_write and not args.task:
        parser.error("--allow-write requires a single task")

    mailbox = Mailbox.from_file(args.seed)
    client = ChatClient()
    print(f"Model: {client.model} @ {client.url}")
    print(f"Mailbox owner: {mailbox.owner} ({len(mailbox.inbox)} emails)\n")

    try:
        if args.task:
            run_task(client, mailbox, args.task, read_only=not args.allow_write)
        else:
            print("Type a task, or 'exit' to quit. The mailbox keeps its state between tasks.")
            while True:
                try:
                    task = input("\nYou: ").strip()
                except EOFError:
                    break
                if task.lower() in ("exit", "quit"):
                    break
                if task:
                    run_task(client, mailbox, task)
    except LLMError as e:
        print(f"LLM error: {e}", file=sys.stderr)
        return 1
    finally:
        print_mailbox_changes(mailbox)
    return 0


if __name__ == "__main__":
    sys.exit(main())
