# Secure Tool Calling

Team Claudian, Track B (Secured agent). This repository holds the **Secure Tool
call** component: the application interface and connected services.

The agent connects a tool-calling model to a synthetic, in-memory mailbox.
The mailbox loads from `data/seed_mailbox.json` on startup. No real email is sent.

## Security controls

| Control | Behavior |
|---|---|
| Read-only by default | The model sees only list, search, and read tools. The registry also blocks write calls if the model proposes one. |
| Argument validation | The registry rejects missing fields, unexpected fields, non-string values, and blank recipients or email IDs before requesting approval. |
| Per-call confirmation | For write-enabled tasks, the CLI previews each send, forward, or delete. Only an explicit `y` in an interactive terminal permits that call. |

The CLI sets the task's permission scope. A model-generated argument cannot
enable write access or approve a call.

## Requirements

- Python 3.11 or later (standard library only, nothing to install)
- An OpenAI-compatible chat endpoint with tool calling. The default is local
  Ollama with `qwen3:14b`:

  ```
  ollama pull qwen3:14b
  ```

## Run

```
python main.py "받은편지함 목록을 보여줘"
python main.py --allow-write "team@example.test에 회의에 참석한다고 메일 보내줘"
python main.py            # interactive mode
```

Tasks are read-only by default. For a single task, `--allow-write` enables
requests to send, forward, or delete mail. Each change previews its details
and requires entering `y` at an interactive terminal.

Each run prints every tool call, the agent's final answer, and the changes made
to the mailbox (sent, forwarded, deleted).

## Offline verification

```sh
python -m unittest -v test_agent_offline
```

The tests replace the model response and use the real agent loop, tool
registry, and synthetic mailbox. They verify that a write proposed during a
read-only task causes zero approval prompts and zero sends, that invalid
arguments are rejected before approval, and that an approved send creates
exactly one outbox entry. No model server is required. These checks measure
whether the harness enforces its policy given a model response.

## Using another model server

Settings are environment variables (see `config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL |
| `LLM_MODEL` | `qwen3:14b` | Model name on that server |
| `LLM_API_KEY` | empty | Sent as a Bearer token when set |
| `LLM_REASONING_EFFORT` | `none` | Turns Qwen3 thinking off on Ollama. Set to an empty string if the server rejects the field |

## Layout

| File | Role |
|---|---|
| `main.py` | CLI |
| `agent.py` | Tool-calling loop |
| `tools.py` | Tool registry and mail tool definitions |
| `mail_store.py` | Synthetic mailbox |
| `llm.py` | Chat client |
| `data/seed_mailbox.json` | Synthetic inbox fixtures |
| `test_agent_offline.py` | Offline tests with scripted model responses |

All tool calls pass through `ToolRegistry.execute()` in `tools.py`, which
checks arguments, the current task's read-only scope, and confirmation before
calling a mailbox function.
