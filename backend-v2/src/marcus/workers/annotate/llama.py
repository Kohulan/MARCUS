"""The MARCUS model behind llama-server (its own container on the GPU, internal network only).

One chat request per paper, as the model was trained and tested (models/qwen3.5-9b-marcus-v1
README): the system prompt plus the paper's input text, the chat template with thinking off,
greedy decoding (temperature 0) under the 11-key grammar (marcus.core.annotation.grammar: the
keys in order, each string within its maxLength, no free whitespace), at most 4,096 output
tokens. llama-server runs with `--parallel 1`, so requests are served one at a time; the q.llm
queue has one slot as well.

Errors (marcus.workers.llamachat): no connection or a 5xx answer -> AnnotatorUnavailable (the
step is retried once); the request's own timeout -> StepTimeout (retried once); a 4xx answer
(e.g. a prompt over the context size) or a reply without a message -> BadResult (final).
Nothing of the paper is logged.
"""

from marcus.core.annotation import MAX_OUTPUT_TOKENS, SYSTEM_PROMPT, grammar
from marcus.workers.llamachat import ModelUnavailable, chat, no_proxy_opener

AnnotatorUnavailable = ModelUnavailable  # llama-server did not answer. Retryable.


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
        self._open = no_proxy_opener()

    def complete(self, text: str) -> str:
        """The model's answer (the JSON text) for one input text."""
        return chat(self._open, self.url, request_body(text), self.timeout_s)["message"]["content"]
