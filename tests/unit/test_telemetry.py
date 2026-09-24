"""Langfuse tracing degrades to a clean no-op when unconfigured — same contract as every other optional Deps
integration (llm=None, vector_store=None, ...). No network calls, no Langfuse import, no errors."""
from omnidata import telemetry
from omnidata.config import Settings


def test_disabled_by_default_with_empty_keys():
    telemetry._enabled = False
    telemetry.init(Settings(langfuse_public_key="", langfuse_secret_key="", langfuse_base_url="", _env_file=None))
    assert telemetry.enabled() is False


def test_observation_is_a_noop_when_disabled():
    telemetry._enabled = False
    with telemetry.observation("span", "handle-message", input="oi") as obs:
        result = obs.update(output="tchau")  # must not raise, must be chainable, must never touch the network
    assert result is obs


def test_trace_attrs_is_a_noop_when_disabled():
    telemetry._enabled = False
    with telemetry.trace_attrs(user_id="u1", session_id="u1", tags=["whatsapp", "text"]):
        pass  # must not raise


def test_init_requires_all_three_keys():
    telemetry._enabled = False
    telemetry.init(Settings(langfuse_public_key="pk-lf-x", langfuse_secret_key="", langfuse_base_url="https://x", _env_file=None))
    assert telemetry.enabled() is False
    telemetry._enabled = False  # reset for other tests
