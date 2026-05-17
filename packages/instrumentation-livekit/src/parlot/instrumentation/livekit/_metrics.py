"""OTLP metrics for Parlot session / turn aggregates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

if TYPE_CHECKING:
    from ._processor import _LiveKitSessionState


def build_meter_provider(endpoint: str, headers: dict[str, str]) -> MeterProvider:
    exporter = OTLPMetricExporter(
        endpoint=endpoint.rstrip("/") + "/v1/metrics",
        headers=headers,
    )
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5_000)
    return MeterProvider(metric_readers=[reader])


class ParlotMetricsRecorder:
  """Records lk.session.* and turn.* metrics mapped to Parlot metric names."""

  def __init__(self, meter_provider: MeterProvider) -> None:
      self._meter = meter_provider.get_meter("parlot.instrumentation.livekit")
      self._turn_e2e = self._meter.create_histogram(
          "turn.e2e_latency_ms",
          unit="ms",
          description="End-to-end latency for one agent turn",
      )
      self._session_turns = self._meter.create_counter(
          "session.turn_count",
          description="Total turns in a session",
      )
      self._session_cost = self._meter.create_counter(
          "session.total_cost_usd",
          unit="USD",
          description="Estimated session LLM cost",
      )
      self._session_input_tokens = self._meter.create_counter(
          "session.total_input_tokens",
          description="Total input tokens in session",
      )
      self._session_output_tokens = self._meter.create_counter(
          "session.total_output_tokens",
          description="Total output tokens in session",
      )

  def record_turn(
      self,
      state: "_LiveKitSessionState",
      *,
      e2e_latency_s: Optional[float],
      interrupted: bool,
  ) -> None:
      attrs = {
          "session.id": state.parlot_session_id,
          "turn.index": state.turn_count,
      }
      if e2e_latency_s is not None:
          self._turn_e2e.record(e2e_latency_s * 1000.0, attributes=attrs)
      if interrupted:
          attrs = {**attrs, "turn.interrupted": True}

  def record_session_close(self, state: "_LiveKitSessionState") -> None:
      attrs = {"session.id": state.parlot_session_id}
      if state.turn_count:
          self._session_turns.add(state.turn_count, attributes=attrs)
      if state.total_cost_usd:
          self._session_cost.add(state.total_cost_usd, attributes=attrs)
      if state.total_input_tokens:
          self._session_input_tokens.add(
              state.total_input_tokens, attributes=attrs
          )
      if state.total_output_tokens:
          self._session_output_tokens.add(
              state.total_output_tokens, attributes=attrs
          )
