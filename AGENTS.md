# Agent Notes (tashan-development-hooks-loop)

## Project Overview

This repo contains a Python Codex `Stop` hook that classifies the final assistant message for Tashan development-loop completion states.

The main goal is not generic hook experimentation. The goal is a reliable local hook that reads `last_assistant_message`, calls an OpenAI-compatible `Responses API`, and returns the correct Codex hook JSON for three completion branches: documentation done, milestone done, and full `vN` task done.

## Quick Commands

All commands are PowerShell commands. Use `;` to chain commands, not `&&`.

- Install / sync dependencies:
  `cd E:\development\tashan-development-hooks-loop ; uv sync`
- Run all tests:
  `cd E:\development\tashan-development-hooks-loop ; uv run pytest -q`
- Run a single test file:
  `cd E:\development\tashan-development-hooks-loop ; uv run pytest tests\test_stop_v_task_classifier.py -q`
- Run local hook with one fixture:
  `cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_doc_done.json | uv run python hooks\stop_v_task_classifier.py`
- Run the globally installed hook with one fixture:
  `Get-Content -Raw E:\development\tashan-development-hooks-loop\tests\fixtures\stop_payload_doc_done.json | & C:\Users\lemon\.codex\hooks\stop_v_task_classifier\.venv\Scripts\python.exe C:\Users\lemon\.codex\hooks\stop_v_task_classifier\stop_v_task_classifier.py`

## Architecture Overview

### Areas

- `hooks/stop_v_task_classifier.py`
  - Stop hook entrypoint
  - stdin payload parsing
  - `.env` loading
  - base URL normalization
  - classifier prompt registry
  - `Responses API` call
  - standard SDK response and raw SSE response parsing
  - final hook JSON output
- `hooks/.env.example`
  - safe template for local configuration
- `hooks/.env`
  - real local credentials, ignored by git
- `tests/fixtures/`
  - canonical Stop payload samples
- `tests/test_stop_v_task_classifier.py`
  - unit, contract, parser, and prompt tests
- `docs/prd/`, `docs/plan/`, `docs/superpowers/specs/`
  - Tashan PRD, plan, and design traceability docs

### Data Flow

```text
Codex Stop payload on stdin
  -> extract last_assistant_message
  -> load hooks/.env
  -> normalize OPENAI_BASE_URL to /v1
  -> OpenAI-compatible Responses API
  -> parse output_text or raw SSE output_text events
  -> JSON classifier result
  -> priority aggregation
  -> Codex hook JSON on stdout
```

### Global Install State

This machine has a global installed copy at:

```text
C:\Users\lemon\.codex\hooks\stop_v_task_classifier
```

Global Codex hook config:

```text
C:\Users\lemon\.codex\hooks.json
```

Current Stop hook command:

```text
"C:\Users\lemon\.codex\hooks\stop_v_task_classifier\.venv\Scripts\python.exe" "C:\Users\lemon\.codex\hooks\stop_v_task_classifier\stop_v_task_classifier.py"
```

Old hook config backup:

```text
C:\Users\lemon\.codex\hooks.json.bak-2026-04-19-stop-v-task
```

## Runtime Configuration

The project-local hook reads:

```text
hooks/.env
```

Required keys:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

`OPENAI_BASE_URL` accepts provider root, `/v1`, or `/v1/responses` preview URLs. The hook normalizes them to a `/v1` base before calling `client.responses.create(...)`.

Do not replace this behavior with hardcoded provider-specific paths.

## Classifier Contract

The branch priority is fixed:

```text
v_task_fully_done > v_milestone_done > v_doc_writing_done
```

Branch messages are fixed:

- `v_doc_writing_done`: `hello World from hooks, on stop event, and v docs have done`
- `v_milestone_done`: `hello World from hooks, on stop event, and v milestone has done`
- `v_task_fully_done`: `hello World from hooks, on stop event, and v task has done`

The prompt must prioritize explicit Tashan completion signals:

```text
TASHAN_COMPLETION_SIGNAL_BEGIN
tashan_version=vN
tashan_status=v_doc_writing_done|v_milestone_done|v_task_fully_done
tashan_milestone=M1|M2|M3|none
tashan_verdict=done
TASHAN_COMPLETION_SIGNAL_END
```

If the signal block is absent, natural-language classification is allowed.

If a message says live smoke, push, merge, remote setup, manual confirmation, or any tail step remains, `v_task_fully_done` must return false.

## Code Style

- Python target: 3.13+
- Package manager: `uv`
- Indentation: 2 spaces in existing Python files; preserve this style.
- Imports: stdlib, third-party, local.
- Keep hook stdout clean. stdout must contain only the Codex hook JSON during normal operation.
- Diagnostic messages, if needed, should go to stderr.
- Do not add broad frameworks or background services. This is a small hook script.

## Testing Strategy

### Required After Code Changes

Run:

```powershell
cd E:\development\tashan-development-hooks-loop ; uv run pytest -q
```

### Required After Parser, Base URL, or Prompt Changes

Run the tests and at least one live fixture smoke if real `.env` is available:

```powershell
cd E:\development\tashan-development-hooks-loop ; Get-Content -Raw tests\fixtures\stop_payload_doc_done.json | uv run python hooks\stop_v_task_classifier.py
```

For release-level confidence, run all four fixtures:

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
  Get-Content -Raw $fixture | uv run python hooks\stop_v_task_classifier.py
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

### Rules

- Add or update tests for every behavior change.
- Keep fixture semantics stable unless the PRD / plan is updated.
- Do not call work complete without fresh verification evidence.
- Live smoke tests are real external API calls; do not run them casually in a tight loop.

## Safety & Conventions

- Do not commit `hooks/.env`.
  - Why: it contains real API credentials.
  - Do instead: commit only `hooks/.env.example`.
  - Verify: `git status --short` must not show `hooks/.env`.
- Do not print secrets.
  - Why: hook logs and terminal history may persist sensitive values.
  - Do instead: print only key names or redacted values.
  - Verify: scan diffs before committing.
- Do not assume all providers return standard SDK `Response` objects.
  - Why: the configured provider may return raw SSE string output.
  - Do instead: preserve `extract_response_text()` and `extract_response_text_from_sse()` compatibility.
  - Verify: `uv run pytest -q`.
- Do not change branch messages casually.
  - Why: downstream hook behavior and tests rely on exact output text.
  - Do instead: update PRD, tests, and docs together if a message must change.
  - Verify: prompt tests and `build_hook_output` tests pass.
- Do not overwrite the global hook config without a backup.
  - Why: a bad global hook can break every Codex Stop event.
  - Do instead: copy `C:\Users\lemon\.codex\hooks.json` to a timestamped backup first.
  - Verify: run the globally installed hook with a fixture.

## Global Install Refresh

To refresh the global installed copy from this repo:

```powershell
$target = 'C:\Users\lemon\.codex\hooks\stop_v_task_classifier'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Force 'E:\development\tashan-development-hooks-loop\hooks\stop_v_task_classifier.py' "$target\stop_v_task_classifier.py"
Copy-Item -Force 'E:\development\tashan-development-hooks-loop\hooks\.env' "$target\.env"
Copy-Item -Force 'E:\development\tashan-development-hooks-loop\hooks\.env.example' "$target\.env.example"
Copy-Item -Force 'E:\development\tashan-development-hooks-loop\pyproject.toml' "$target\pyproject.toml"
uv sync --project $target --python 3.13
```

Then verify:

```powershell
Get-Content -Raw E:\development\tashan-development-hooks-loop\tests\fixtures\stop_payload_doc_done.json | & C:\Users\lemon\.codex\hooks\stop_v_task_classifier\.venv\Scripts\python.exe C:\Users\lemon\.codex\hooks\stop_v_task_classifier\stop_v_task_classifier.py
```

## Documentation Policy

If behavior changes, update all relevant docs in the same change:

- `README.md`
- `AGENTS.md`
- `docs/prd/PRD-0001-stop-hook-v-task-classifier.md`
- `docs/superpowers/specs/2026-04-19-stop-hook-ai-classifier-design.md`
- `docs/plan/v1-stop-hook-ai-classifier.md`

Do not let prompt behavior, parser behavior, or install instructions drift from docs.

## Scope & Precedence

- This root `AGENTS.md` applies to the entire repo.
- A future subdirectory `AGENTS.md` overrides this file for that subtree.
- `AGENTS.override.md` in the same directory overrides `AGENTS.md`.
- The user's explicit chat instructions always take precedence.
- Global `~/.codex/AGENTS.md` may add personal defaults, but project-specific rules here govern this repo.

