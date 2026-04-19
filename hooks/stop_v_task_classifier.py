from __future__ import annotations

import importlib
import json
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx


BRANCH_MESSAGES = {
  "v_milestone_done": "hello World from hooks, on stop event, and v milestone has done",
  "v_task_fully_done": "hello World from hooks, on stop event, and v task has done",
}

DOCS_REVIEW_CONTINUATION_PROMPT = (
  "请使用subagent调用与主会话同样的模型，对刚完成的文档做一次完整的业务逻辑上的review，并将返回来的中肯的"
  "review意见，由主会话做出修正；如果subagent给出的review意见，属于鸡毛蒜皮，无伤大雅，那么请主会话直接开始下一步的"
  "落地实现，不要纠结于文档"
)

COMPLETION_SIGNAL_RULES = """If the message contains a machine-readable completion signal block with exact markers:
TASHAN_COMPLETION_SIGNAL_BEGIN
...
TASHAN_COMPLETION_SIGNAL_END
treat that block as the highest-priority evidence.
The signal block uses keys including tashan_version, tashan_status, tashan_milestone, and tashan_verdict.
If the signal block is present and tashan_verdict is not done, return false.
If the signal block is present and tashan_status belongs to another classifier, return false.
If no signal block is present, fall back to natural-language classification of the full message."""

CLASSIFIER_DEFINITIONS = {
  "v_doc_writing_done": {
    "prompt": f"""You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that the documentation-writing phase for a v-series task has been completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_doc_writing_done.
{COMPLETION_SIGNAL_RULES}
Return true immediately when the signal block is present with tashan_status=v_doc_writing_done and tashan_verdict=done.
When matching from the signal block, copy tashan_version into version when available, and use milestone_id=null unless the message explicitly provides one.
Return true only when the message clearly states the docs were written, saved, or landed, often with concrete artifacts such as PRD, plan, spec, or file paths.
Also return true when the message clearly says the docs were revised, written back, updated into specific files, or changed documents are already landed, even if implementation is described as the next step.
You may infer version from explicit versioned document file names or paths such as v1-index.md or v25-*.md.
If the message is only planning, drafting, or asking for review before docs are written, return false.""",
  },
  "v_milestone_done": {
    "prompt": f"""You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that one milestone M inside a v-series task has been completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_milestone_done.
{COMPLETION_SIGNAL_RULES}
Return true immediately when the signal block is present with tashan_status=v_milestone_done and tashan_verdict=done.
When matching from the signal block, copy tashan_version into version and copy tashan_milestone into milestone_id unless it is none.
Return true when the message clearly states M1, M2, M3, or another milestone inside vN is complete, even if the full vN is not complete.
Return false if the message only lists milestone names, describes milestone planning, or says implementation will proceed by milestones without explicitly saying one milestone has already completed.
Return false if the message only says work is in progress or does not identify a completed milestone.""",
  },
  "v_task_fully_done": {
    "prompt": f"""You are a strict classifier for a Codex Stop hook.
Decide whether the assistant's final message explicitly indicates that an entire v-series task has been fully completed.
Return only one JSON object with keys: classifier_id, is_match, version, milestone_id, reason.
classifier_id must be v_task_fully_done.
{COMPLETION_SIGNAL_RULES}
Return true immediately when the signal block is present with tashan_status=v_task_fully_done and tashan_verdict=done.
Return true only if the message clearly indicates the whole vN scope is complete.
If the message says there is still live smoke, push, merge, remote setup, manual confirmation, or another remaining tail step, return false.
If the message only says one milestone M is done, part of the code is done, docs are done, or more implementation/testing/verification remains, return false.""",
  },
}

CLASSIFIER_PRIORITY = [
  "v_task_fully_done",
  "v_milestone_done",
  "v_doc_writing_done",
]

SUPPORTED_WIRE_APIS = ("responses", "chat_completions_stream")
DEFAULT_CHAT_STREAM_TIMEOUT_SECONDS = 180.0


@dataclass(frozen=True)
class ProviderConfig:
  name: str
  api_key: str
  base_url: str
  model: str
  wire_apis: tuple[str, ...]


@dataclass(frozen=True)
class ProviderAttemptSuccess:
  provider_name: str
  wire_api: str
  text_length: int
  result: dict[str, Any]


@dataclass(frozen=True)
class ProviderAttemptFailure:
  provider_name: str
  wire_api: str
  error_type: str
  error_message: str


def get_log_path(script_path: Path) -> Path:
  return script_path.with_name("stop_v_task_classifier.log")


def append_log_event(log_path: Path, event: str, **fields: Any) -> None:
  payload = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "event": event,
    **fields,
  }
  log_path.parent.mkdir(parents=True, exist_ok=True)
  with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def try_append_log_event(log_path: Path, event: str, *, stderr: Any, **fields: Any) -> None:
  try:
    append_log_event(log_path, event, **fields)
  except Exception as exc:
    print(
      f"Stop hook logging failed. path={log_path} error={type(exc).__name__}: {exc}",
      file=stderr,
    )


def extract_last_assistant_message(payload: dict[str, Any]) -> str:
  message = payload.get("last_assistant_message")
  if not isinstance(message, str) or not message.strip():
    raise RuntimeError("Stop payload missing last_assistant_message")
  return message


def extract_response_text_from_sse(response_text: str) -> str:
  current_event = ""
  collected_deltas: list[str] = []

  for line in response_text.splitlines():
    if line.startswith("event: "):
      current_event = line[len("event: ") :].strip()
      continue
    if not line.startswith("data: "):
      continue

    payload = line[len("data: ") :].strip()
    if not payload or payload == "[DONE]":
      continue

    item = json.loads(payload)
    event_type = str(item.get("type") or current_event)

    if event_type == "response.output_text.done":
      text = item.get("text")
      if isinstance(text, str) and text:
        return text

    if event_type == "response.output_text.delta":
      delta = item.get("delta")
      if isinstance(delta, str):
        collected_deltas.append(delta)

  if collected_deltas:
    return "".join(collected_deltas)

  raise RuntimeError("Responses API SSE payload did not contain output text")


def extract_response_text(response: Any) -> str:
  if isinstance(response, str):
    if response.lstrip().startswith("event: "):
      return extract_response_text_from_sse(response)
    return response

  output_text = getattr(response, "output_text", None)
  if isinstance(output_text, str):
    if output_text.lstrip().startswith("event: "):
      return extract_response_text_from_sse(output_text)
    return output_text

  raise RuntimeError("Responses API response did not expose output_text")


def normalize_base_url(raw_base_url: str) -> str:
  value = raw_base_url.strip().rstrip("/")
  parsed = urlsplit(value)
  if not parsed.scheme or not parsed.netloc:
    raise RuntimeError("OPENAI_BASE_URL must be an absolute URL")

  path = parsed.path.rstrip("/")
  if path.endswith("/responses"):
    path = path[: -len("/responses")]
  if not path.endswith("/v1"):
    path = f"{path}/v1" if path else "/v1"

  return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def import_runtime_module(module_name: str) -> Any:
  if sys.modules.get(module_name) is None:
    sys.modules.pop(module_name, None)
  return importlib.import_module(module_name)


def load_runtime_dependencies() -> tuple[Any, Any]:
  try:
    dotenv_module = import_runtime_module("dotenv")
    openai_module = import_runtime_module("openai")
  except Exception as exc:
    raise RuntimeError("Hook bootstrap dependency import failed") from exc

  dotenv_values = getattr(dotenv_module, "dotenv_values", None)
  openai_class = getattr(openai_module, "OpenAI", None)
  if dotenv_values is None:
    raise RuntimeError("python-dotenv dotenv_values is unavailable during hook bootstrap")
  if openai_class is None:
    raise RuntimeError("openai.OpenAI is unavailable during hook bootstrap")
  return dotenv_values, openai_class


def load_settings(env_path: Path, *, dotenv_values_func: Any | None = None) -> dict[str, str]:
  if dotenv_values_func is None:
    dotenv_values_func, _ = load_runtime_dependencies()
  values = dotenv_values_func(env_path)
  api_key = values.get("OPENAI_API_KEY")
  base_url = values.get("OPENAI_BASE_URL")
  model = values.get("OPENAI_MODEL")
  missing = [
    name
    for name, value in {
      "OPENAI_API_KEY": api_key,
      "OPENAI_BASE_URL": base_url,
      "OPENAI_MODEL": model,
    }.items()
    if not value
  ]
  if missing:
    raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
  return {
    "api_key": str(api_key),
    "base_url": normalize_base_url(str(base_url)),
    "model": str(model),
  }


def parse_wire_apis(raw_value: str) -> tuple[str, ...]:
  wire_apis = tuple(item.strip() for item in raw_value.split(",") if item.strip())
  if not wire_apis:
    raise RuntimeError("Provider config must declare at least one wire api")
  invalid = [item for item in wire_apis if item not in SUPPORTED_WIRE_APIS]
  if invalid:
    raise RuntimeError(f"Unsupported wire apis: {', '.join(invalid)}")
  return wire_apis


def build_legacy_provider(values: dict[str, Any]) -> ProviderConfig:
  api_key = values.get("OPENAI_API_KEY")
  base_url = values.get("OPENAI_BASE_URL")
  model = values.get("OPENAI_MODEL")
  missing = [
    name
    for name, value in {
      "OPENAI_API_KEY": api_key,
      "OPENAI_BASE_URL": base_url,
      "OPENAI_MODEL": model,
    }.items()
    if not value
  ]
  if missing:
    raise RuntimeError(f"Missing required .env keys: {', '.join(missing)}")
  return ProviderConfig(
    name="default",
    api_key=str(api_key),
    base_url=normalize_base_url(str(base_url)),
    model=str(model),
    wire_apis=("responses",),
  )


def load_provider_chain_settings(
  env_path: Path,
  *,
  dotenv_values_func: Any | None = None,
) -> list[ProviderConfig]:
  if dotenv_values_func is None:
    dotenv_values_func, _ = load_runtime_dependencies()
  values = dotenv_values_func(env_path)

  if not values.get("HOOK_PROVIDER_1_BASE_URL"):
    return [build_legacy_provider(values)]

  providers: list[ProviderConfig] = []
  index = 1
  while values.get(f"HOOK_PROVIDER_{index}_BASE_URL"):
    prefix = f"HOOK_PROVIDER_{index}_"
    name = values.get(f"{prefix}NAME") or f"provider_{index}"
    api_key = values.get(f"{prefix}API_KEY")
    base_url = values.get(f"{prefix}BASE_URL")
    model = values.get(f"{prefix}MODEL")
    wire_apis = values.get(f"{prefix}WIRE_APIS")
    missing = [
      field
      for field, value in {
        "API_KEY": api_key,
        "BASE_URL": base_url,
        "MODEL": model,
        "WIRE_APIS": wire_apis,
      }.items()
      if not value
    ]
    if missing:
      raise RuntimeError(f"Provider {index} missing fields: {', '.join(missing)}")
    providers.append(
      ProviderConfig(
        name=str(name),
        api_key=str(api_key),
        base_url=normalize_base_url(str(base_url)),
        model=str(model),
        wire_apis=parse_wire_apis(str(wire_apis)),
      )
    )
    index += 1
  return providers


def parse_classifier_response_text(raw_text: str, *, source: str) -> dict[str, Any]:
  if not raw_text.strip():
    if source == "responses":
      raise RuntimeError(
        "Responses API returned an empty response body for /responses; "
        "provider may not support the endpoint correctly"
      )
    raise RuntimeError(f"{source} returned an empty response body")
  try:
    result = json.loads(raw_text)
  except json.JSONDecodeError as exc:
    preview = raw_text[:200].replace("\r", "\\r").replace("\n", "\\n")
    raise RuntimeError(
      f"{source} returned non-JSON output for classifier parsing. "
      f"preview={preview!r}"
    ) from exc
  if "classifier_id" not in result or "is_match" not in result:
    raise RuntimeError("Classifier JSON missing classifier_id or is_match")
  return result


def run_provider_attempt(
  provider: ProviderConfig,
  wire_api: str,
  classifier_definition: dict[str, str],
  message: str,
  *,
  openai_client_factory: Any,
  chat_stream_requester: Any | None,
) -> ProviderAttemptSuccess:
  if wire_api != "responses":
    raise RuntimeError(f"Unsupported wire api in responses transport: {wire_api}")
  client = openai_client_factory(api_key=provider.api_key, base_url=provider.base_url)
  response = client.responses.create(
    model=provider.model,
    input=[
      {"role": "system", "content": classifier_definition["prompt"]},
      {"role": "user", "content": message},
    ],
  )
  raw_text = extract_response_text(response)
  result = parse_classifier_response_text(raw_text, source="responses")
  return ProviderAttemptSuccess(
    provider_name=provider.name,
    wire_api="responses",
    text_length=len(raw_text),
    result=result,
  )


def extract_chat_completions_text_from_sse(response_text: str) -> str:
  chunks: list[str] = []
  for line in response_text.splitlines():
    if not line.startswith("data: "):
      continue
    payload = line[len("data: ") :].strip()
    if not payload or payload == "[DONE]":
      continue
    item = json.loads(payload)
    choices = item.get("choices") or []
    if not choices:
      continue
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
      chunks.append(content)
  if not chunks:
    raise RuntimeError("chat_completions_stream SSE did not contain assistant content")
  return "".join(chunks)


def default_chat_stream_requester(
  provider: ProviderConfig,
  prompt: str,
  message: str,
) -> str:
  payload = {
    "model": provider.model,
    "messages": [
      {"role": "system", "content": prompt},
      {"role": "user", "content": message},
    ],
    "stream": True,
  }
  with httpx.Client(timeout=DEFAULT_CHAT_STREAM_TIMEOUT_SECONDS) as client:
    with client.stream(
      "POST",
      f"{provider.base_url}/chat/completions",
      headers={
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
      },
      json=payload,
    ) as response:
      response.raise_for_status()
      return "".join(response.iter_text())


def classify_last_message_with_provider_chain(
  providers: list[ProviderConfig],
  classifier_definition: dict[str, str],
  message: str,
  *,
  openai_client_factory: Any,
  chat_stream_requester: Any | None,
  attempt_logger: Any | None,
) -> dict[str, Any]:
  requester = default_chat_stream_requester if chat_stream_requester is None else chat_stream_requester
  failures: list[ProviderAttemptFailure] = []

  for provider in providers:
    for wire_api in provider.wire_apis:
      if attempt_logger is not None:
        attempt_logger("attempt", provider, wire_api)
      try:
        if wire_api == "responses":
          success = run_provider_attempt(
            provider,
            wire_api,
            classifier_definition,
            message,
            openai_client_factory=openai_client_factory,
            chat_stream_requester=requester,
          )
        elif wire_api == "chat_completions_stream":
          raw_text = extract_chat_completions_text_from_sse(
            requester(provider, classifier_definition["prompt"], message)
          )
          success = ProviderAttemptSuccess(
            provider_name=provider.name,
            wire_api=wire_api,
            text_length=len(raw_text),
            result=parse_classifier_response_text(raw_text, source=wire_api),
          )
        else:
          raise RuntimeError(f"Unsupported wire api: {wire_api}")
      except Exception as exc:
        failures.append(
          ProviderAttemptFailure(
            provider_name=provider.name,
            wire_api=wire_api,
            error_type=type(exc).__name__,
            error_message=str(exc),
          )
        )
        if attempt_logger is not None:
          attempt_logger("failure", provider, wire_api, error=exc)
        continue

      if attempt_logger is not None:
        attempt_logger("success", provider, wire_api, text_length=success.text_length)
      return success.result

  if attempt_logger is not None:
    attempt_logger("chain_failure", None, None, failures=failures)
  raise RuntimeError(
    "All provider attempts failed: "
    + "; ".join(f"{item.provider_name}/{item.wire_api} -> {item.error_message}" for item in failures)
  )


def classify_last_message(
  client: Any,
  settings: dict[str, str],
  classifier_definition: dict[str, str],
  message: str,
) -> dict[str, Any]:
  response = client.responses.create(
    model=settings["model"],
    input=[
      {"role": "system", "content": classifier_definition["prompt"]},
      {"role": "user", "content": message},
    ],
  )
  raw_text = extract_response_text(response)
  return parse_classifier_response_text(raw_text, source="responses")


def build_hook_output(classifications: list[dict[str, Any]]) -> dict[str, Any]:
  matches = {
    item.get("classifier_id"): item
    for item in classifications
    if item.get("is_match") is True
  }
  for classifier_id in CLASSIFIER_PRIORITY:
    if classifier_id in matches:
      if classifier_id == "v_doc_writing_done":
        return {
          "continue": True,
          "decision": "block",
          "reason": DOCS_REVIEW_CONTINUATION_PROMPT,
        }
      return {"continue": True, "systemMessage": BRANCH_MESSAGES[classifier_id]}
  return {"continue": True}


def build_attempt_logger(log_path: Path, stderr: Any):
  def _log(
    event_type: str,
    provider: ProviderConfig | None,
    wire_api: str | None,
    *,
    error: Exception | None = None,
    text_length: int | None = None,
    failures: list[ProviderAttemptFailure] | None = None,
  ) -> None:
    if event_type == "attempt" and provider is not None and wire_api is not None:
      try_append_log_event(
        log_path,
        "provider_attempt",
        stderr=stderr,
        provider_name=provider.name,
        base_url=provider.base_url,
        wire_api=wire_api,
        model=provider.model,
      )
      return
    if event_type == "failure" and provider is not None and wire_api is not None and error is not None:
      try_append_log_event(
        log_path,
        "provider_attempt_failure",
        stderr=stderr,
        provider_name=provider.name,
        wire_api=wire_api,
        error_type=type(error).__name__,
        error_message=str(error),
      )
      return
    if event_type == "success" and provider is not None and wire_api is not None:
      try_append_log_event(
        log_path,
        "provider_attempt_success",
        stderr=stderr,
        provider_name=provider.name,
        wire_api=wire_api,
        text_length=text_length,
      )
      return
    if event_type == "chain_failure" and failures is not None:
      try_append_log_event(
        log_path,
        "provider_chain_failure",
        stderr=stderr,
        attempts=[
          {
            "provider_name": item.provider_name,
            "wire_api": item.wire_api,
            "error_type": item.error_type,
            "error_message": item.error_message,
          }
          for item in failures
        ],
      )
  return _log


def run_hook(
  payload: Any,
  *,
  env_path: Path,
  script_path: Path,
  client_factory: Any = None,
  chat_stream_requester: Any = None,
  stderr: Any = sys.stderr,
) -> tuple[dict[str, Any] | None, int]:
  log_path = get_log_path(script_path)
  payload_is_dict = isinstance(payload, dict)
  try_append_log_event(
    log_path,
    "hook_start",
    stderr=stderr,
    payload_type=type(payload).__name__,
    hook_event_name=payload.get("hook_event_name") if payload_is_dict else None,
    payload_keys=sorted(payload.keys()) if payload_is_dict else [],
    has_last_assistant_message=payload_is_dict and isinstance(payload.get("last_assistant_message"), str),
    last_assistant_message_length=len(payload.get("last_assistant_message", "")) if payload_is_dict and isinstance(payload.get("last_assistant_message"), str) else 0,
  )

  try:
    if not payload_is_dict:
      raise RuntimeError("Stop payload must be a JSON object")
    message = extract_last_assistant_message(payload)
    dotenv_values_func, openai_client_factory = load_runtime_dependencies()
    providers = load_provider_chain_settings(env_path, dotenv_values_func=dotenv_values_func)
    primary_provider = providers[0]
    try_append_log_event(
      log_path,
      "settings_loaded",
      stderr=stderr,
      env_path=str(env_path),
      base_url=primary_provider.base_url,
      model=primary_provider.model,
      provider_count=len(providers),
      last_assistant_message_length=len(message),
    )
    if client_factory is None:
      client_factory = openai_client_factory
    attempt_logger = build_attempt_logger(log_path, stderr)
    classifications: list[dict[str, Any]] = []
    for classifier_id, classifier_definition in CLASSIFIER_DEFINITIONS.items():
      result = classify_last_message_with_provider_chain(
        providers,
        classifier_definition,
        message,
        openai_client_factory=client_factory,
        chat_stream_requester=chat_stream_requester,
        attempt_logger=attempt_logger,
      )
      classifications.append(result)
      try_append_log_event(
        log_path,
        "classifier_result",
        stderr=stderr,
        classifier_id=classifier_id,
        is_match=result.get("is_match"),
        version=result.get("version"),
        milestone_id=result.get("milestone_id"),
      )
    output = build_hook_output(classifications)
    try_append_log_event(
      log_path,
      "hook_success",
      stderr=stderr,
      has_system_message="systemMessage" in output,
      system_message=output.get("systemMessage"),
      decision=output.get("decision"),
      has_reason="reason" in output,
      reason_length=len(output.get("reason", "")) if isinstance(output.get("reason"), str) else 0,
    )
    return output, 0
  except Exception as exc:
    try_append_log_event(
      log_path,
      "hook_failure",
      stderr=stderr,
      error_type=type(exc).__name__,
      error_message=str(exc),
      traceback=traceback.format_exc(),
    )
    print(f"Stop hook failed. See {log_path}", file=stderr)
    return None, 1


def main() -> int:
  script_path = Path(__file__)
  log_path = get_log_path(script_path)
  try:
    payload = json.load(sys.stdin)
  except Exception as exc:
    try_append_log_event(
      log_path,
      "payload_parse_failure",
      stderr=sys.stderr,
      error_type=type(exc).__name__,
      error_message=str(exc),
      traceback=traceback.format_exc(),
    )
    print(f"Stop hook failed. See {log_path}", file=sys.stderr)
    return 1
  output, exit_code = run_hook(
    payload,
    env_path=script_path.with_name(".env"),
    script_path=script_path,
  )
  if output is not None:
    json.dump(output, sys.stdout, ensure_ascii=False)
  return exit_code


if __name__ == "__main__":
  raise SystemExit(main())
