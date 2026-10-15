"""Server-to-PostgreSQL actor assertions for the P0-02 prototype.

This module does not authenticate a user. Callers may construct
AuthenticatedSession only from a server-side session lookup; never from HTTP
headers, query parameters, cookies decoded by the client, or request JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import time
import uuid


_ACTIONS = frozenset({"submit", "presentation", "approve", "post"})


@dataclass(frozen=True)
class AuthenticatedSession:
    """Identity values resolved by the trusted app session store."""

    actor_id: uuid.UUID
    session_id: uuid.UUID


@dataclass(frozen=True)
class ActorAssertion:
    nonce: uuid.UUID
    issued_epoch: int
    key_id: str
    signature: str


def assertion_message(
    session: AuthenticatedSession,
    action: str,
    nonce: uuid.UUID,
    issued_epoch: int,
    scope: str,
) -> bytes:
    if action not in _ACTIONS:
        raise ValueError("unsupported actor action")
    if not scope or len(scope) > 512:
        raise ValueError("invalid actor assertion scope")
    fields = (
        "webdebit-actor-assertion-v1",
        str(session.actor_id),
        str(session.session_id),
        action,
        str(nonce),
        str(issued_epoch),
        scope,
    )
    return "\n".join(fields).encode("utf-8")


def sign_actor_assertion(
    session: AuthenticatedSession,
    action: str,
    scope: str,
    *,
    key_id: str,
    key: bytes,
    issued_epoch: int | None = None,
    nonce: uuid.UUID | None = None,
) -> ActorAssertion:
    """Sign one short-lived, single-use DB action from a server session."""
    if len(key) < 32:
        raise ValueError("actor signing key must be at least 32 bytes")
    if not key_id or len(key_id) > 64:
        raise ValueError("invalid signing key id")
    issued = int(time.time()) if issued_epoch is None else int(issued_epoch)
    action_nonce = uuid.uuid4() if nonce is None else nonce
    message = assertion_message(session, action, action_nonce, issued, scope)
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    return ActorAssertion(action_nonce, issued, key_id, signature)


def submit_scope(proposal_id: int | None, payload_text: str) -> str:
    body_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
    target = "new" if proposal_id is None else str(proposal_id)
    return f"submit:{target}:{body_hash}"


def presentation_scope(proposal_id: int, title: str) -> str:
    title_hash = hashlib.sha256(title.encode("utf-8")).hexdigest()
    return f"presentation:{proposal_id}:{title_hash}"


def revision_scope(action: str, proposal_id: int, revision_id: int, content_sha256: str) -> str:
    if action not in {"approve", "post"} or len(content_sha256) != 64:
        raise ValueError("invalid revision scope")
    return f"{action}:{proposal_id}:{revision_id}:{content_sha256}"
