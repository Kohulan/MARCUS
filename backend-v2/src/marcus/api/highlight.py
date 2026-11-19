"""Signed highlights (security F5): `/tools/depict` never searches with a pattern it did not make.

A subgraph search is exponential for a pattern that does not occur in the molecule, and a
running JNI call cannot be interrupted. So a highlight is accepted only with a token that
`POST /tools/mcs` issued with its SMARTS: an HMAC over the SMARTS and the molecules the MCS was
computed from, valid for TOKEN_TTL_S. `/tools/depict` draws the highlight only for one of those
molecules, where the pattern is a known substructure in RDKit's model, the one that made it.
The tools worker therefore matches it in RDKit on the drawn SMILES (found at once, at most
MAX_HIGHLIGHT_MAPPINGS mappings walked) and CDK only draws the matched atoms: CDK's aromaticity
differs (a tellurophene is aromatic to RDKit, not to CDK), and its search could miss.

Molecules are compared by `binding key`: RDKit's canonical SMILES without stereo, of the MCS's
molfiles (read as the tools worker reads them) and of the SMILES to draw, both computed here.
The MCS (CompareElements, CompareOrder) carries no stereo, so a pattern found in a molfile also
occurs in a SMILES of the same graph whatever its stereo. The token holds sha256 digests only.

The key: MARCUS_HIGHLIGHT_KEY when set, else one random key per deployment, made by the first
API process that needs it and shared through Redis (`REDIS_KEY`), so every API process checks
the tokens every other one issued. It is never logged. A Redis restart makes a new key; tokens
issued before it are refused (the client asks /tools/mcs again).
"""

import base64
import hashlib
import hmac
import json
import secrets
import time

from rdkit import Chem
from rdkit.rdBase import BlockLogs

from marcus.core.settings import get_settings

TOKEN_TTL_S = 30 * 60
REDIS_KEY = "marcus:highlight_key"
_CONTEXT = b"marcus-highlight-v1."
INVALID = "highlight not valid for this structure"


def _now() -> float:
    return time.time()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _key_of(mol) -> str | None:
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, isomericSmiles=False) or None


def binding_key_of_smiles(smiles: str) -> str | None:
    """The binding key of a SMILES to draw, or None when RDKit cannot read it. CPU-bound: run
    it in marcus.api.chempool."""
    _block = BlockLogs()  # noqa: F841
    return _key_of(Chem.MolFromSmiles(smiles))


def _mol_from_molfile(molfile: str):
    """As marcus.workers.tools reads an MCS input: sanitized, else unsanitized then
    sanitized; None when neither works."""
    mol = Chem.MolFromMolBlock(molfile, sanitize=True)
    if mol is None:
        try:
            mol = Chem.MolFromMolBlock(molfile, sanitize=False)
            if mol is not None:
                Chem.SanitizeMol(mol)
        except (ValueError, RuntimeError):
            mol = None
    return mol


def binding_keys_of_molfiles(molfiles: list[str]) -> list[str]:
    """The binding keys of the molfiles an MCS was computed from (unreadable ones are left out,
    as the worker leaves them out). CPU-bound: run it in marcus.api.chempool."""
    _block = BlockLogs()  # noqa: F841
    keys = (_key_of(_mol_from_molfile(m)) for m in molfiles)
    return sorted({k for k in keys if k})


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: bytes, payload: str) -> str:
    return _b64(hmac.new(key, _CONTEXT + payload.encode("ascii"), hashlib.sha256).digest())


def sign(key: bytes, smarts: str, binding_keys: list[str], now: float | None = None) -> str:
    """A token for `smarts` over the molecules with these binding keys, valid TOKEN_TTL_S."""
    issued = _now() if now is None else now
    claims = {
        "e": int(issued + TOKEN_TTL_S),
        "s": digest(smarts),
        "m": sorted({digest(k) for k in binding_keys}),
    }
    payload = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    return f"{payload}.{_mac(key, payload)}"


def verify(key: bytes, token: str, smarts: str, binding_key: str | None) -> bool:
    """True only for a token this deployment signed, not expired, for this exact SMARTS, with
    `binding_key` (the drawn molecule's) among its molecules."""
    if binding_key is None or token.count(".") != 1:
        return False
    payload, mac = token.split(".")
    try:
        if not hmac.compare_digest(_mac(key, payload), mac):
            return False
        claims = json.loads(_unb64(payload))
    except (ValueError, UnicodeError):
        return False
    if not isinstance(claims, dict):
        return False
    expires, pattern, molecules = claims.get("e"), claims.get("s"), claims.get("m")
    if type(expires) is not int or expires < _now():
        return False
    if not isinstance(molecules, list) or pattern != digest(smarts):
        return False
    return digest(binding_key) in molecules


async def signing_key(redis) -> bytes:
    """MARCUS_HIGHLIGHT_KEY, else the deployment's shared random key in Redis (made once,
    SET NX). Redis errors are the caller's to handle."""
    configured = get_settings().highlight_key
    if configured is not None:
        return configured.get_secret_value().encode()
    await redis.set(REDIS_KEY, secrets.token_hex(32), nx=True)
    value = await redis.get(REDIS_KEY)
    if not value:
        raise OSError("highlight key missing")
    return value
