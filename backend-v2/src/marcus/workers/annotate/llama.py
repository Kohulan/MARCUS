"""The MARCUS model behind llama-server (its own container on the GPU, internal network only).

One chat request per paper, as the model was trained and tested (models/qwen3.5-9b-marcus-v1
README): the system prompt plus the paper's input text, the chat template with thinking off,
greedy decoding (temperature 0) under the 11-key grammar (marcus.core.annotation.grammar: the
keys in order, each string within its maxLength, no free whitespace), at most 4,096 output
tokens. llama-server runs with `--parallel 1`, so requests are served one at a time; the q.llm
queue has one slot as well.

Errors: no connection or a 5xx answer -> AnnotatorUnavailable (the step is retried once); the
request's own timeout -> StepTimeout (retried once); a 4xx answer (e.g. a prompt over the
context size) or a reply without a message -> BadResult (final). Nothing of the paper is logged.
"""

import json
import socket
import urllib.error
import urllib.request

from marcus.core.annotation import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, grammar
from marcus.core.pipeline import BadResult
from marcus.workers.runtime import StepTimeout

MAX_REPLY_BYTES = 1 << 20  # the 11 fields are at most ~12 k characters


class AnnotatorUnavailable(Exception):
    """llama-server did not answer (down, starting, overloaded). Retryable."""


def request_body(text: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "grammar": grammar(),
        "chat_template_kwargs": {"enable_thinking": False},
        "stream": False,
    }


class LlamaAnnotator:
    def __init__(self, url: str, timeout_s: float, model: str, version: str):
        self.url = url.rstrip("/") + "/v1/chat/completions"
        self.timeout_s = timeout_s
        self.model = model
        self.version = version
        # no proxy from the environment: the server is on the internal network
        self._open = urllib.request.build_opener(urllib.request.ProxyHandler({})).open

    def complete(self, text: str) -> str:
        """The model's answer (the JSON text) for one input text."""
        data = json.dumps(request_body(text)).encode("utf-8")
        req = urllib.request.Request(
            self.url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with self._open(req, timeout=self.timeout_s) as resp:
                body = resp.read(MAX_REPLY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                raise AnnotatorUnavailable(f"llama-server answered {exc.code}") from None
            raise BadResult(f"llama-server refused the request ({exc.code})") from None
        except (TimeoutError, socket.timeout) as exc:
            raise StepTimeout("llama-server did not answer in time") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError | socket.timeout):
                raise StepTimeout("llama-server did not answer in time") from exc
            raise AnnotatorUnavailable(f"llama-server unreachable: {exc.reason}") from None
        except (ConnectionError, OSError) as exc:
            raise AnnotatorUnavailable(f"llama-server unreachable: {type(exc).__name__}") from None
        if len(body) > MAX_REPLY_BYTES:
            raise BadResult("llama-server reply is too large")
        try:
            content = json.loads(body)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise BadResult("llama-server reply has no message") from None
        if not isinstance(content, str):
            raise BadResult("llama-server reply has no message")
        return content
