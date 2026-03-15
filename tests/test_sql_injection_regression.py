"""
SQL Injection regression tests for the Dispute Replay Tool.

These tests verify that the emitter and replay engine always use psycopg2
parameterised queries — ensuring malicious input is never embedded directly
into a SQL string. They act as a regression guard against future refactoring
that accidentally reverts to unsafe string formatting.

All tests mock psycopg2 so no live database is required.

Run with:
    python -m pytest tests/test_sql_injection_regression.py -v
"""

import json
import unittest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# Shared injection payloads
# ---------------------------------------------------------------------------

INJECTION_STRINGS = [
    # Classic termination + new statement
    "'; DROP TABLE events; --",
    # Always-true bypass
    "' OR '1'='1",
    # UNION-based data exfiltration
    "' UNION SELECT username, password, null, null, null, null, null FROM users --",
    # Stacked queries
    "TXN-001'; INSERT INTO events VALUES ('x','x','x',now(),'x',null,'{}'); --",
    # Comment injection
    "TXN-001' --",
    # Null byte
    "TXN-001\x00' OR '1'='1",
    # Nested quotes
    "TXN-001'' OR ''1''=''1",
    # Semicolon alone
    "TXN-001;",
    # Oversized input — DoS / column length probe
    "A" * 10_000,
]


# ---------------------------------------------------------------------------
# Helper: build a fully mocked psycopg2 connection
# ---------------------------------------------------------------------------

def _mock_conn():
    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    return mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Emitter tests
# ---------------------------------------------------------------------------

class TestEmitterSQLInjection(unittest.TestCase):
    """
    Verify that EventEmitter passes all values through psycopg2 parameterised
    queries. The SQL string must NEVER be formatted with user input directly.
    """

    def _run_emit(
        self,
        transaction_id: str,
        extra_payload: dict = None,
        event_type: str = "document.received",
        model_version: str | None = None,
    ):
        """Invoke EventEmitter.emit() with a mocked DB and return the cursor mock."""
        mock_conn, mock_cursor = _mock_conn()

        env = {
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "PIPELINE_VERSION": "1.0.0",
        }

        with patch("psycopg2.connect", return_value=mock_conn), \
             patch.dict("os.environ", env, clear=False):
            # Import here so env vars are already set
            from replay_tool.emitter import EventEmitter
            emitter = EventEmitter(transaction_id=transaction_id)
            emitter.emit(
                event_type,
                payload=extra_payload or {"file_name": "test.pdf"},
                model_version=model_version,
            )

        return mock_cursor

    def test_injected_transaction_id_is_parameterised(self):
        """
        For every injection string used as a transaction_id, the SQL template
        must remain unchanged and the value must appear only in the parameters
        tuple — never inside the SQL string itself.
        """
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(transaction_id=injection)
                execute_call: call = cursor.execute.call_args

                sql_string: str = execute_call[0][0]
                params: tuple = execute_call[0][1]

                # The raw injection string must NOT appear in the SQL template
                self.assertNotIn(
                    injection,
                    sql_string,
                    msg=f"Injection string leaked into SQL template for: {injection[:60]!r}",
                )
                # The transaction_id must appear in the parameters tuple
                self.assertIn(
                    injection,
                    params,
                    msg=f"transaction_id missing from params for: {injection[:60]!r}",
                )

    def test_injected_payload_value_is_json_serialised(self):
        """
        When an injection string appears inside the payload dict, it must be
        JSON-serialised and passed as a parameter — not embedded in SQL.
        """
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(
                    transaction_id="TXN-SAFE",
                    extra_payload={"file_name": injection},
                )
                execute_call = cursor.execute.call_args
                sql_string: str = execute_call[0][0]
                params: tuple = execute_call[0][1]

                # The raw injection must NOT be in the SQL
                self.assertNotIn(injection, sql_string)

                # The payload parameter must be a JSON string containing the injection
                payload_param = params[-1]
                self.assertIsInstance(payload_param, str)
                parsed = json.loads(payload_param)
                self.assertEqual(parsed["file_name"], injection)

    def test_sql_template_never_changes(self):
        """
        The INSERT SQL template must be identical across all injection attempts.
        """
        expected_sql = (
            "\nINSERT INTO events\n"
            "    (event_id, transaction_id, event_type, timestamp,\n"
            "     pipeline_version, model_version, payload)\n"
            "VALUES\n"
            "    (%s, %s, %s, %s, %s, %s, %s)\n"
        )
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(transaction_id=injection)
                actual_sql: str = cursor.execute.call_args[0][0]
                self.assertEqual(
                    actual_sql,
                    expected_sql,
                    msg="SQL template was mutated by injection input",
                )

    def test_params_tuple_always_has_seven_elements(self):
        """
        The parameters tuple must always have exactly 7 elements matching the
        7 placeholders in the INSERT statement. Injection must not split or
        expand the tuple.
        """
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(transaction_id=injection)
                params: tuple = cursor.execute.call_args[0][1]
                self.assertEqual(
                    len(params),
                    7,
                    msg=f"Expected 7 params, got {len(params)} for: {injection[:60]!r}",
                )

    def test_injected_model_version_is_parameterised(self):
        """
        model_version is an optional user-supplied string passed as a parameter.
        Injection through this field must not reach the SQL template.
        """
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(
                    transaction_id="TXN-SAFE",
                    event_type="extraction.completed",
                    extra_payload={"extracted_fields": {}},
                    model_version=injection,
                )
                sql_string: str = cursor.execute.call_args[0][0]
                params: tuple = cursor.execute.call_args[0][1]
                self.assertNotIn(
                    injection,
                    sql_string,
                    msg=f"model_version injection leaked into SQL for: {injection[:60]!r}",
                )
                self.assertIn(
                    injection,
                    params,
                    msg=f"model_version missing from params for: {injection[:60]!r}",
                )

    def test_injected_event_type_string_is_parameterised(self):
        """
        event_type accepts a raw str in addition to the EventType enum.
        Injection through this field must not reach the SQL template.
        """
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_emit(
                    transaction_id="TXN-SAFE",
                    event_type=injection,
                )
                sql_string: str = cursor.execute.call_args[0][0]
                params: tuple = cursor.execute.call_args[0][1]
                self.assertNotIn(
                    injection,
                    sql_string,
                    msg=f"event_type injection leaked into SQL for: {injection[:60]!r}",
                )
                self.assertIn(
                    injection,
                    params,
                    msg=f"event_type missing from params for: {injection[:60]!r}",
                )


# ---------------------------------------------------------------------------
# Replay engine tests
# ---------------------------------------------------------------------------

class TestReplayEngineSQLInjection(unittest.TestCase):
    """
    Verify that get_events() passes the transaction_id as a parameter,
    never formatting it into the SELECT SQL string.
    """

    def _run_get_events(self, transaction_id: str):
        """Invoke get_events() with a mocked DB and return the cursor mock."""
        mock_conn, mock_cursor = _mock_conn()
        # Return an empty result set — we're only checking the query call
        mock_cursor.fetchall.return_value = []

        env = {"DATABASE_URL": "postgresql://test:test@localhost/test"}

        with patch("psycopg2.connect", return_value=mock_conn), \
             patch.dict("os.environ", env, clear=False):
            from replay_tool.replay_engine import get_events
            get_events(transaction_id)

        return mock_cursor

    def test_injected_transaction_id_is_parameterised(self):
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_get_events(transaction_id=injection)
                execute_call = cursor.execute.call_args

                sql_string: str = execute_call[0][0]
                params: tuple = execute_call[0][1]

                self.assertNotIn(
                    injection,
                    sql_string,
                    msg=f"Injection string leaked into SELECT SQL for: {injection[:60]!r}",
                )
                self.assertIn(
                    injection,
                    params,
                    msg=f"transaction_id missing from SELECT params for: {injection[:60]!r}",
                )

    def test_params_tuple_always_has_one_element(self):
        """SELECT uses exactly one placeholder (%s) for transaction_id."""
        for injection in INJECTION_STRINGS:
            with self.subTest(injection=injection[:60]):
                cursor = self._run_get_events(transaction_id=injection)
                params: tuple = cursor.execute.call_args[0][1]
                self.assertEqual(
                    len(params),
                    1,
                    msg=f"Expected 1 param, got {len(params)} for: {injection[:60]!r}",
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
