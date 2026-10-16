"""Unit checks for the server-side actor assertion envelope."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

from actor_assertion import (  # noqa: E402
    AuthenticatedSession,
    assertion_message,
    revision_scope,
    sign_actor_assertion,
    submit_scope,
)


class ActorAssertionTests(unittest.TestCase):
    def setUp(self):
        self.session = AuthenticatedSession(
            uuid.UUID("11111111-1111-4111-8111-111111111111"),
            uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )
        self.nonce = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        self.key = b"k" * 32

    def signature(self, *, session=None, action="approve", scope="approve:7:9:abc",
                  nonce=None, issued=1_800_000_000):
        return sign_actor_assertion(session or self.session, action, scope,
            key_id="test-key", key=self.key, nonce=nonce or self.nonce,
            issued_epoch=issued).signature

    def test_same_server_session_envelope_is_deterministic(self):
        self.assertEqual(self.signature(), self.signature())

    def test_signature_changes_with_actor_session_action_nonce_or_scope(self):
        changes = (
            {"session": AuthenticatedSession(uuid.uuid4(), self.session.session_id)},
            {"session": AuthenticatedSession(self.session.actor_id, uuid.uuid4())},
            {"action": "post"},
            {"scope": "approve:7:10:abc"},
            {"nonce": uuid.uuid4()},
            {"issued": 1_800_000_001},
        )
        original = self.signature()
        for changed in changes:
            with self.subTest(changed=changed):
                self.assertNotEqual(original, self.signature(**changed))

    def test_action_scope_helpers_bind_content_identity(self):
        self.assertNotEqual(submit_scope(None, "payload-a"), submit_scope(None, "payload-b"))
        self.assertEqual(revision_scope("approve", 7, 9, "a" * 64),
                         "approve:7:9:" + "a" * 64)
        self.assertEqual(revision_scope("confirm_price", 7, 9, "b" * 64),
                         "confirm_price:7:9:" + "b" * 64)
        self.assertEqual(revision_scope("confirm_period", 7, 9, "c" * 64),
                         "confirm_period:7:9:" + "c" * 64)
        with self.assertRaises(ValueError):
            revision_scope("reject", 7, 9, "a" * 64)

    def test_message_rejects_client_defined_action_and_invalid_scope(self):
        with self.assertRaises(ValueError):
            assertion_message(self.session, "admin_override", self.nonce, 1, "scope")
        with self.assertRaises(ValueError):
            assertion_message(self.session, "approve", self.nonce, 1, "")
        with self.assertRaises(ValueError):
            assertion_message(self.session, "approve", self.nonce, 1, "x" * 513)

    def test_short_signing_key_is_refused(self):
        with self.assertRaises(ValueError):
            sign_actor_assertion(self.session, "approve", "approve:7:9:abc",
                key_id="test-key", key=b"short", nonce=self.nonce, issued_epoch=1)


if __name__ == "__main__":
    unittest.main()
