"""Exercise the real agent loop with scripted model replies and in-memory mail."""

import json
import unittest
from unittest.mock import Mock, patch

from agent import run_agent
from llm import ChatClient
from mail_store import Mailbox
from main import confirm_tool
from tools import build_mail_tools


# 지정한 도구 호출을 담은 모의 모델 응답을 만든다.
def tool_reply(name, arguments, call_id):
    return {
        "content": "",
        "tool_calls": [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        }],
    }


class OfflineAgentTest(unittest.TestCase):
    # 각 테스트에서 사용할 빈 메일함과 읽기 전용 도구를 준비한다.
    def setUp(self):
        self.mailbox = Mailbox("owner@example.test", [])
        self.registry = build_mail_tools(self.mailbox)

    # 승인된 발송이 한 건 기록되고 같은 호출 ID로 결과가 반환되는지 확인한다.
    def test_sends_mail_and_returns_result_to_model(self):
        arguments = {"to": "team@example.test", "subject": "Meeting", "body": "I can attend."}
        confirm = Mock(return_value=True)
        registry = build_mail_tools(self.mailbox, read_only=False, confirm=confirm)
        client = Mock(spec=ChatClient)

        # 첫 요청에 발송을 제안하고 다음 응답 전에 도구 실행 결과를 확인한다.
        def chat(messages, tools):
            if messages[-1]["role"] == "user":
                self.assertIn("send_email", [tool["function"]["name"] for tool in tools])
                return tool_reply("send_email", json.dumps(arguments), "call-send")

            tool_message = messages[-1]
            self.assertEqual(tool_message["role"], "tool")
            self.assertEqual(tool_message["tool_call_id"], "call-send")
            self.assertEqual(json.loads(tool_message["content"])["status"], "sent")
            return {"content": "Sent the meeting reply."}

        client.chat.side_effect = chat
        result = run_agent(client, registry, self.mailbox.owner, "Send the meeting reply.")

        confirm.assert_called_once_with("send_email", arguments)
        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(result.final_text, "Sent the meeting reply.")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(len(self.mailbox.sent), 1)
        self.assertEqual({key: self.mailbox.sent[0][key] for key in arguments}, arguments)

    # 등록되지 않은 도구 호출이 거부되는지 확인한다.
    def test_rejects_unregistered_tool(self):
        self.check_rejected_call("unregistered_tool", "{}", "Unknown tool")

    # 깨진 JSON 인자가 도구 실행 전에 거부되는지 확인한다.
    def test_rejects_malformed_json(self):
        self.check_rejected_call("send_email", "{", "not a valid JSON object")

    # 읽기 전용 모드에서 모델이 전달을 제안해도 승인 요청 없이 차단되는지 확인한다.
    def test_read_only_blocks_unadvertised_write_from_model(self):
        confirm = Mock(return_value=True)
        self.registry = build_mail_tools(self.mailbox, confirm=confirm)
        self.assertEqual(
            {schema["function"]["name"] for schema in self.registry.schemas()},
            {"list_inbox", "search_emails", "read_email"},
        )
        self.assertEqual(json.loads(self.registry.execute("list_inbox", {})), [])
        self.check_rejected_call(
            "forward_email", '{"email_id":"m1","to":"team@example.test"}', "read_only",
        )
        confirm.assert_not_called()

    # 인자가 잘못된 경우 승인 콜백을 부르지 않는지 확인한다.
    def test_invalid_arguments_do_not_prompt(self):
        confirm = Mock(return_value=True)
        self.registry = build_mail_tools(self.mailbox, read_only=False, confirm=confirm)
        for arguments in (
            {"subject": "Meeting", "body": ""},
            {"to": 7, "subject": "Meeting", "body": ""},
            {"to": "  ", "subject": "Meeting", "body": ""},
            {"to": "team@example.test", "subject": "", "body": "", "approved": True},
        ):
            with self.subTest(arguments=arguments):
                self.check_rejected_call("send_email", json.dumps(arguments), "invalid_arguments")
        confirm.assert_not_called()

    # 승인 콜백이 없거나 사용자가 승인하지 않으면 실행하지 않는지 확인한다.
    def test_write_requires_explicit_confirmation(self):
        for confirm, error in (
            (None, "confirmation_required"),
            (Mock(return_value=False), "confirmation_denied"),
            (Mock(side_effect=EOFError), "confirmation_denied"),
        ):
            with self.subTest(error=error):
                self.registry = build_mail_tools(self.mailbox, read_only=False, confirm=confirm)
                self.check_rejected_call(
                    "send_email", '{"to":"team@example.test","subject":"","body":""}', error,
                )

    # 전달 승인과 삭제 취소가 각각 반영되고 원문이 미리보기에 들어가는지 확인한다.
    def test_forward_and_delete_preview_and_apply_separate_decisions(self):
        original = {
            "id": "m1", "from": "sender@example.test", "subject": "Meeting",
            "body": "Original", "date": "2026-11-23",
        }
        mailbox = Mailbox(self.mailbox.owner, [original])
        confirm = Mock(side_effect=[True, False])
        registry = build_mail_tools(mailbox, read_only=False, confirm=confirm)
        forward = {"email_id": "m1", "to": "team@example.test"}
        self.assertEqual(json.loads(registry.execute("forward_email", forward))["status"], "forwarded")
        self.assertEqual(json.loads(registry.execute("delete_email", {"email_id": "m1"}))["error"],
                         "confirmation_denied")
        self.assertEqual(len(mailbox.sent), 1)
        self.assertEqual(mailbox.deleted, [])
        self.assertEqual(mailbox.read("m1"), original)
        self.assertEqual(confirm.call_args_list[0].args[1]["original_body_to_be_forwarded"], "Original")

    # 표준 입력이 터미널이 아니면 승인 입력을 받지 않는지 확인한다.
    @patch("builtins.input")
    @patch("main.sys.stdin.isatty", return_value=False)
    def test_cli_does_not_accept_piped_approval(self, isatty, read_input):
        self.assertFalse(confirm_tool("send_email", {}))
        read_input.assert_not_called()

    # 거부 사유가 모델에 반환되고 모의 발송이 없는지 공통으로 확인한다.
    def check_rejected_call(self, name, arguments, expected_error):
        client = Mock(spec=ChatClient)

        # 첫 요청에 테스트용 호출을 반환하고 다음 요청에서 거부 사유를 검사한다.
        def chat(messages, tools):
            if messages[-1]["role"] == "user":
                return tool_reply(name, arguments, "call-error")

            tool_message = messages[-1]
            self.assertEqual(tool_message["role"], "tool")
            self.assertEqual(tool_message["tool_call_id"], "call-error")
            self.assertIn(expected_error, json.loads(tool_message["content"])["error"])
            return {"content": "The tool request failed."}

        client.chat.side_effect = chat
        result = run_agent(client, self.registry, self.mailbox.owner, "Check the mailbox.")

        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(result.final_text, "The tool request failed.")
        self.assertEqual(self.mailbox.sent, [])


if __name__ == "__main__":
    unittest.main()
