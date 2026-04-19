# Tashan Development Hooks Loop

Codex `Stop` hook prototype for detecting Tashan development-loop completion signals.

The hook reads `last_assistant_message` from a Codex Stop payload, calls an OpenAI-compatible `Responses API`, classifies the final assistant message into one of three Tashan completion branches, and returns a Codex hook JSON response.

## What It Detects

The hook currently supports three classifier branches, in priority order:

1. `v_task_fully_done`
   - Entire `vN` task is fully complete.
   - Output: `hello World from hooks, on stop event, and v task has done`
2. `v_milestone_done`
   - A single milestone such as `M1`, `M2`, or `M3` is complete, but the whole `vN` may not be complete.
   - Output: `hello World from hooks, on stop event, and v milestone has done`
3. `v_doc_writing_done`
   - The PRD / spec / plan documentation phase is complete.
   - Output: `hello World from hooks, on stop event, and v docs have done`

If nothing matches, the hook returns:

```json
{"continue": true}
```

## Completion Signal

The hook first looks for the explicit machine-readable Tashan signal block. If present, the block is treated as the strongest evidence:

```text
TASHAN_COMPLETION_SIGNAL_BEGIN
tashan_version=vN
tashan_status=v_doc_writing_done|v_milestone_done|v_task_fully_done
tashan_milestone=M1|M2|M3|none
tashan_verdict=done
TASHAN_COMPLETION_SIGNAL_END
```

If this block is absent, the hook falls back to natural-language classification through the configured model.

## Project Layout

```text
.
├── hooks/
│   ├── stop_v_task_classifier.py   # Stop hook entrypoint
│   ├── .env.example                # Safe local config template
│   └── .env                        # Real local config, ignored by git
├── tests/
│   ├── fixtures/                   # Stop payload examples
│   └── test_stop_v_task_classifier.py
├── docs/
│   ├── prd/
│   ├── plan/
│   └── superpowers/specs/
├── pyproject.toml
└── uv.lock
```

## Configuration

Create `hooks/.env` from `hooks/.env.example`:

```env
OPENAI_API_KEY=replace-me
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-mini
```

`OPENAI_BASE_URL` accepts these forms:

- Provider root: `https://www.right.codes/codex`
- Standard base URL: `https://www.right.codes/codex/v1`
- Pasted preview URL: `https://www.right.codes/codex/v1/responses`

The hook normalizes all of them to a `Responses API`-compatible `/v1` base before calling `client.responses.create(...)`.

Do not commit `hooks/.env`. It contains real credentials.

## Development Commands

All commands below are PowerShell commands.

Install / sync dependencies:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv sync
```

Run the test suite:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest -q
```

Dry-run the global installer:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --dry-run
```

Refresh the global hook install:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py
```

Refresh the global hook install and run a live docs smoke:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --smoke
```

Run one fixture through the local project hook:

```powershell
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_doc_done.json | uv run python hooks\stop_v_task_classifier.py
```

Run all live fixture smokes against the configured provider:

```powershell
cd E:\development\tashan-development-hooks-loop
$fixtures = @(
  'tests/fixtures/stop_payload_doc_done.json',
  'tests/fixtures/stop_payload_milestone_done.json',
  'tests/fixtures/stop_payload_v_task_done.json',
  'tests/fixtures/stop_payload_not_done.json'
)
foreach ($fixture in $fixtures) {
  Write-Output "=== $fixture ==="
  Get-Content -Raw $fixture | uv run python hooks/stop_v_task_classifier.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## Global Codex Hook Install

Current global install path on this machine:

```text
C:\Users\lemon\.codex\hooks\stop_v_task_classifier
```

The global copy includes:

- `stop_v_task_classifier.py`
- `.env`
- `.env.example`
- `pyproject.toml`
- `.venv`

The active global Codex hook config is:

```text
C:\Users\lemon\.codex\hooks.json
```

The current Stop command points at:

```text
C:\Users\lemon\.codex\hooks\stop_v_task_classifier\.venv\Scripts\python.exe C:\Users\lemon\.codex\hooks\stop_v_task_classifier\stop_v_task_classifier.py
```

Previous global hook config backup:

```text
C:\Users\lemon\.codex\hooks.json.bak-2026-04-19-stop-v-task
```

If Codex does not pick up the new hook immediately, restart Codex so it reloads `hooks.json`.

## Reinstall Global Hook

Use the repo-local Python installer:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py
```

Recommended verification:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --smoke
```

What the installer does:

- syncs only changed files into `C:\Users\lemon\.codex\hooks\stop_v_task_classifier`
- copies `.env` and `.env.example`
- compares `pyproject.toml` and `uv.lock`; only runs `uv sync` when dependency files changed
- parses `C:\Users\lemon\.codex\hooks.json`
- leaves `hooks.json` untouched when the Stop command is already correct
- replaces the old `hello_world.py` Stop command when present
- adds the correct Stop command without overwriting unrelated Stop commands
- creates a timestamped `hooks.json` backup only when a real JSON write is required

Useful options:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --dry-run
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --force-hooks-json
cd E:\development\tashan-development-hooks-loop ; uv run python scripts\install_global_stop_hook.py --target C:\custom\codex\hooks\stop_v_task_classifier --hooks-json C:\custom\codex\hooks.json
```

## Provider Response Compatibility

Some OpenAI-compatible providers return a normal SDK response object with `output_text`.

This hook also supports providers that return raw SSE text containing events such as:

- `response.output_text.delta`
- `response.output_text.done`
- `response.completed`

The parser extracts the final model text from `response.output_text.done`, or falls back to accumulated `response.output_text.delta` chunks.

## Security Notes

- Never commit `hooks/.env` or the copied global `.env`.
- Never paste real API keys into docs, tests, commit messages, or issue text.
- Keep `hooks/.env.example` as the only tracked config example.
- Treat live fixture smoke tests as real external API calls.

## Current Verification Baseline

At the time this README was written:

- Unit / contract tests: `uv run pytest -q` -> `15 passed`
- Live fixture smoke against configured provider:
  - docs fixture -> docs branch message
  - milestone fixture -> milestone branch message
  - full-v fixture -> task branch message
  - not-done fixture -> `{"continue": true}`
