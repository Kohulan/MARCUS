"""One chat request to a llama-server on the internal network (the MARCUS model for annotation,
the R-group model for R-group definitions): the shared HTTP part and its error mapping.

Errors: no connection or a 5xx answer -> ModelUnavailable (the step is retried once); the
request's own timeout -> StepTimeout (retried once); a 4xx answer (e.g. a prompt over the
context size), a reply over MAX_REPLY_BYTES or a reply without a message -> BadResult (final).
Nothing of the paper is logged; proxies from the environment are never used.
"""

import json
import socket
import urllib.error
import urllib.request

from marcus.core.pipeline import BadResult
from marcus.workers.runtime import StepTimeout

MAX_REPLY_BYTES = 1 << 20  # the 11 annotation fields are at most ~12 k characters, rows less


class ModelUnavailable(Exception):
    """llama-server did not answer (down, starting, overloaded). Retryable."""


def chat(open_, url: str, body: dict, timeout_s: float, server: str = "llama-server") -> dict:
    """POST one chat request to a llama-server (`url`: its /v1/chat/completions) with `open_`
    (an opener without proxies) and return the reply's first choice, whose message content is a
    string. The error mapping of this module's docstring."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with open_(req, timeout=timeout_s) as resp:
            reply = resp.read(MAX_REPLY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            raise ModelUnavailable(f"{server} answered {exc.code}") from None
        raise BadResult(f"{server} refused the request ({exc.code})") from None
    except (TimeoutError, socket.timeout) as exc:
        raise StepTimeout(f"{server} did not answer in time") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError | socket.timeout):
            raise StepTimeout(f"{server} did not answer in time") from exc
        raise ModelUnavailable(f"{server} unreachable: {exc.reason}") from None
    except (ConnectionError, OSError) as exc:
        raise ModelUnavailable(f"{server} unreachable: {type(exc).__name__}") from None
    if len(reply) > MAX_REPLY_BYTES:
        raise BadResult(f"{server} reply is too large")
    try:
        choice = json.loads(reply)["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise BadResult(f"{server} reply has no message") from None
    if not isinstance(content, str):
        raise BadResult(f"{server} reply has no message")
    return choice


def no_proxy_opener():
    """urlopen without proxies from the environment: the servers are on the internal network."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open
