"""CLI for the baseline mail agent.

    python main.py "받은편지함 목록 보여줘"     one task, then exit
    python main.py                              interactive mode
"""

import argparse
import json
import sys

import config
from agent import ToolCallRecord, run_agent
from llm import ChatClient, LLMError
from mail_store import Mailbox
from tools import build_mail_tools


def print_tool_call(record: ToolCallRecord) -> None:
    args = json.dumps(record.arguments, ensure_ascii=False)
    result = record.result if len(record.result) <= 300 else record.result[:300] + "..."
    print(f"  [tool] {record.name}({args})")
    print(f"         -> {result}")


def print_mailbox_changes(mailbox: Mailbox) -> None:
    print("\n=== Mailbox changes ===")
    if not mailbox.sent and not mailbox.deleted:
        print("(none)")
    for m in mailbox.sent:
        kind = "FORWARDED" if "forwarded_from" in m else "SENT"
        print(f"{kind} to {m['to']} | {m['subject']}")
    for m in mailbox.deleted:
        print(f"DELETED {m['id']} | {m['subject']}")


def run_task(client: ChatClient, mailbox: Mailbox, task: str) -> None:
    registry = build_mail_tools(mailbox)
    result = run_agent(client, registry, mailbox.owner, task, on_tool_call=print_tool_call)
    print(f"\nAgent: {result.final_text}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Baseline mail agent (synthetic mailbox)")
    parser.add_argument("task", nargs="?", help="Task for the agent. Omit for interactive mode.")
    parser.add_argument("--seed", default=str(config.SEED_MAILBOX), help="Seed mailbox JSON file")
    args = parser.parse_args()

    mailbox = Mailbox.from_file(args.seed)
    client = ChatClient()
    print(f"Model: {client.model} @ {client.url}")
    print(f"Mailbox owner: {mailbox.owner} ({len(mailbox.inbox)} emails)\n")

    try:
        if args.task:
            run_task(client, mailbox, args.task)
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
