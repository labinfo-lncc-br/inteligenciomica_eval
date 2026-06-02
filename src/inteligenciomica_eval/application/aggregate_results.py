from __future__ import annotations

import dataclasses
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from inteligenciomica_eval.domain.ports import ResultReaderPort
from inteligenciomica_eval.domain.services.aggregation import (
    AggregationService,
    ConfigAggregate,
)

_log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


def _nan_to_null(obj: Any) -> Any:
    """Converte recursivamente float NaN em None para serialização JSON válida (RFC 8259).

    ``json.dumps`` com ``allow_nan=True`` produz tokens ``NaN`` que não são JSON
    válido. Esta função substitui NaN por ``None`` (serializado como ``null``)
    antes de chamar ``json.dumps``.
    """
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nan_to_null(v) for v in obj]
    return obj


@dataclass(frozen=True)
class AggregateResultsInput:
    """Input DTO para AggregateResultsUseCase.

    Args:
        run_id: identificador do run de avaliação.
        round_id: identificador da rodada (ex.: ``"round_1"``).
        phase: fase do experimento (``"A"`` ou ``"B"``); ``None`` carrega ambas.
        failure_threshold: limiar de falha para ``EvaluationResult.is_failure``.
    """

    run_id: str
    round_id: str
    phase: str | None = None
    failure_threshold: float = 0.70


@dataclass(frozen=True)
class AggregateResultsOutput:
    """Output DTO do AggregateResultsUseCase.

    Args:
        run_id: identificador do run de avaliação.
        round_id: identificador da rodada.
        aggregates: tupla de ``ConfigAggregate`` ordenada por ``rank_score`` desc.
        n_total_results: total de resultados carregados (antes de exclusão NaN).
        n_nan_excluded: soma de ``n_excluded_nan`` de todos os agregados.
        n_configs: número de configurações agregadas.
        best_config: configuração com o maior ``rank_score``.
    """

    run_id: str
    round_id: str
    aggregates: tuple[ConfigAggregate, ...]
    n_total_results: int
    n_nan_excluded: int
    n_configs: int
    best_config: ConfigAggregate


def _rank_key(agg: ConfigAggregate) -> float:
    """Chave de ordenação por rank_score — NaN vai para o fim."""
    v = agg.rank_score.value
    return v if not math.isnan(v) else float("-inf")


class AggregateResultsUseCase:
    """Orquestra a agregação de EvaluationResults por configuração {base, llm}.

    Lê resultados via ``ResultReaderPort``, delega 100% da lógica de agregação
    ao ``AggregationService`` injetado, ordena por ``rank_score`` descrescente e
    persiste um sumário JSON em ``data_dir``. Nenhuma lógica de agregação é
    reimplementada aqui (§14.7, TAREFA-403; Nota M4 item 8).

    Args:
        reader: port de leitura de resultados.
        aggregation_service: serviço de domínio injetado (não instanciado internamente).
        data_dir: diretório onde o arquivo JSON de sumário será gravado.
    """

    def __init__(
        self,
        reader: ResultReaderPort,
        aggregation_service: AggregationService,
        data_dir: Path,
    ) -> None:
        self._reader = reader
        self._aggregation_service = aggregation_service
        self._data_dir = data_dir

    def execute(self, inp: AggregateResultsInput) -> AggregateResultsOutput:
        """Agrega resultados e persiste sumário JSON.

        Args:
            inp: parâmetros de entrada (run_id, round_id, phase, failure_threshold).

        Returns:
            :class:`AggregateResultsOutput` com agregados ordenados e metadados.
        """
        t0 = time.monotonic()

        frame = self._reader.load(
            round_id=inp.round_id,
            phase=inp.phase,
            run_id=inp.run_id,
        )
        n_total = len(frame.results)

        raw_aggregates = self._aggregation_service.aggregate_all(
            frame.results,
            threshold=inp.failure_threshold,
        )

        aggregates = tuple(sorted(raw_aggregates, key=_rank_key, reverse=True))

        if not aggregates:
            raise ValueError(
                f"No results found for run_id={inp.run_id!r}, "
                f"round_id={inp.round_id!r}, phase={inp.phase!r}. "
                "Cannot aggregate an empty result set."
            )

        best_config = aggregates[0]
        n_nan_excluded = sum(a.n_excluded_nan for a in aggregates)

        output_path = self._data_dir / f"{inp.run_id}_{inp.round_id}_aggregates.json"
        summary = _nan_to_null([dataclasses.asdict(a) for a in aggregates])
        output_path.write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        _log.info(
            "aggregate_results_completed",
            run_id=inp.run_id,
            round_id=inp.round_id,
            n_configs=len(aggregates),
            n_nan_excluded=n_nan_excluded,
            best_config_base=best_config.base.value,
            best_config_llm=best_config.llm.value,
            best_config_rank_score=best_config.rank_score.value,
            latency_ms=latency_ms,
        )

        return AggregateResultsOutput(
            run_id=inp.run_id,
            round_id=inp.round_id,
            aggregates=aggregates,
            n_total_results=n_total,
            n_nan_excluded=n_nan_excluded,
            n_configs=len(aggregates),
            best_config=best_config,
        )
