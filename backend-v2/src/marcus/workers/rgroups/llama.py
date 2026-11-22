"""The R-group model behind its own llama-server (`llama-rgroup`: the GPU, internal network only).

One chat request per scaffold, as the model was trained and tested (MARCUS-training
models/nuextract3-rgroup-v1/README.md): marcus.core.rgroup_extraction.request_body, sent as
json.dumps writes it (the bake-off client's bytes). llama-server runs with `--parallel 1`; the
q.rgroup queue has one slot. Errors as marcus.workers.llamachat maps them (no connection or 5xx:
retried once; timeout: retried once; 4xx or no message: final).
"""

from marcus.core.rgroup_extraction import request_body
from marcus.workers.llamachat import chat, no_proxy_opener

SERVER = "llama-rgroup"


class LlamaRgroupReader:
    def __init__(self, url: str, timeout_s: float, model: str, version: str):
        self.url = url.rstrip("/") + "/v1/chat/completions"
        self.timeout_s = timeout_s
        self.model = model
        self.version = version
        self._open = no_proxy_opener()

    def read(self, labels: list[str], context: str, image_uri: str) -> tuple[str, bool]:
        """The model's answer (the JSON text) and whether the token limit cut it."""
        body = request_body(self.model, labels, context, image_uri)
        choice = chat(self._open, self.url, body, self.timeout_s, server=SERVER)
        return choice["message"]["content"], choice.get("finish_reason") == "length"
