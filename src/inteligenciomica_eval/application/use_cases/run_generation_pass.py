"""RunGenerationPassUseCase — Passada 1 da arquitetura de 3 passadas (ADR-004).

Orquestra ``RetrieverPort`` + ``GeneratorPort`` para cada célula
``{fase x base x llm x seed x pergunta}``, implementando idempotência (ADR-009)
e tolerância a falhas por célula (``GenerationError``). NÃO computa métricas —
isso é responsabilidade das passadas 2 e 3 (``RunMetricsPassUseCase`` e
``RunJudgePassUseCase``).

Padrão clean-architecture §2: o use case orquestra ports injetados por DI, sem
importar ``infrastructure`` (import-linter Contract 2/4) e sem duplicar lógica de
domínio. ``structlog`` É permitido na camada ``application`` (CLAUDE.md §4).

Desvios conscientes em relação à spec (TAREFA-304):

1. ``config: RunConfigView`` (Protocol estrutural) em vez de ``RoundConfig`` Pydantic.
   Application NÃO pode importar infrastructure (import-linter Contract 2/4); o
   ``RoundConfig`` satisfaz este Protocol por duck-typing (mesmo padrão do
   ``RoundConfigView`` de TAREFA-303).

2. ``execute`` recebe ``questions: Sequence[Question]`` explicitamente porque não
   há port de dataset: a spec lista ``wave_plan`` mas as perguntas têm que vir de
   algum lugar — o orquestrador (TAREFA-309) as carrega e passa como argumento.

3. ``max_retries`` é parâmetro do construtor (default 3) para injetabilidade em
   testes — mesma convenção de ``_retry_stop``/``_retry_wait`` dos adapters de M1.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import structlog

from inteligenciomica_eval.application.services.wave_scheduler import WavePlan
from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.errors import ConfigValidationError, GenerationError
from inteligenciomica_eval.domain.ports import (
    Chunk,
    GeneratorPort,
    ResultReaderPort,
    ResultWriterPort,
    RetrieverPort,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)

_log = structlog.get_logger(__name__)

_NAN = float("nan")
_PHASE_B_BASE = "fixed"
_ALL_NAN_METRICS = MetricVector(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
    bertscore_f1=_NAN,
    rubric_biomed_score=_NAN,
)


class _RetrievalView(Protocol):
    """Vista estrutural mínima da configuração de retrieval."""

    top_k: int


class RunConfigView(Protocol):
    """Vista estrutural mínima da configuração de rodada para o use case de geração.

    A camada ``application`` NÃO importa ``RoundConfig`` (infrastructure — import-linter
    Contract 2/4); depende desta abstração que ``RoundConfig`` satisfaz estruturalmente
    (inversão de dependência, ADR-001). Mesmo padrão do ``RoundConfigView`` de TAREFA-303.

    Campos de proveniência (TAREFA-311, ADR-014):
    - ``server_mode``: ``"managed"`` ou ``"external"``.
    - ``generator_served_model_ids``: mapa ``{llm_name: served_model_id}`` preenchido
      pelo wiring a partir dos probes de endpoint (nunca inventado).
    - ``judge_determinism_verified``: resultado medido do probe de determinismo do juiz.
    """

    phases: list[str]
    bases: list[str]
    seeds: list[int]
    temperature: float
    retrieval: _RetrievalView
    server_mode: str
    generator_served_model_ids: dict[str, str]
    judge_determinism_verified: bool


@dataclass(frozen=True, slots=True)
class GenerationPassReport:
    """Relatório de execução da Passada 1 de geração (ADR-004).

    Args:
        run_id: identificador da rodada.
        wave_plan: plano de ondas executado.
        n_generated: linhas persistidas com sucesso.
        n_skipped: linhas puladas por idempotência (ADR-009).
        n_errors: células com falha permanente após esgotar max_retries.
        duration_s: duração total da passada em segundos.
        failed_cells: row_ids (hex SHA-256) das células com erro permanente.
    """

    run_id: str
    wave_plan: WavePlan
    n_generated: int
    n_skipped: int
    n_errors: int
    duration_s: float
    failed_cells: tuple[str, ...]


class RunGenerationPassUseCase:
    """Passada 1 da arquitetura de 3 passadas (ADR-004): recupera, gera e persiste.

    Args:
        retriever: port de recuperação vetorial (Experimento A).
        generator: port de geração de texto (vLLM).
        writer: port de persistência de resultados (idempotente via ADR-009).
        reader: port de leitura — mantido por compatibilidade de assinatura com a spec;
            a verificação de idempotência usa ``writer.exists()``.
        config: vista estrutural da configuração de rodada (ver :class:`RunConfigView`).
        max_retries: tentativas máximas por célula em ``GenerationError`` (default 3).
    """

    def __init__(
        self,
        *,
        retriever: RetrieverPort,
        generator: GeneratorPort,
        writer: ResultWriterPort,
        reader: ResultReaderPort,
        config: RunConfigView,
        max_retries: int = 3,
    ) -> None:
        self._retriever = retriever
        self._generator = generator
        self._writer = writer
        self._reader = reader
        self._config = config
        self._max_retries = max_retries

    async def execute(
        self,
        *,
        run_id: str,
        wave_plan: WavePlan,
        questions: Sequence[Question],
        canonical_contexts: dict[str, list[Chunk]] | None = None,
    ) -> GenerationPassReport:
        """Executa a passada de geração para todas as ondas do plano.

        Args:
            run_id: identificador da rodada (proveniência, ADR-009).
            wave_plan: plano de ondas produzido por :class:`WaveSchedulerService`.
            questions: perguntas do benchmark (RF1: 13 perguntas curadas).
            canonical_contexts: mapa ``question_id → chunks`` para o Experimento B.
                Obrigatório quando ``"B"`` está em ``config.phases``.

        Returns:
            :class:`GenerationPassReport` com totais e células com falha permanente.

        Raises:
            ConfigValidationError: se ``"B"`` em ``config.phases`` e
                ``canonical_contexts`` é ``None``.
        """
        if "B" in self._config.phases and canonical_contexts is None:
            raise ConfigValidationError(
                "canonical_contexts",
                "Experiment B requires canonical_contexts "
                "(config.phases includes 'B' but canonical_contexts is None).",
            )

        t_start = time.monotonic()
        n_generated = 0
        n_skipped = 0
        n_errors = 0
        failed_cells: list[str] = []
        cell_count = 0

        for wave in wave_plan.waves:
            _log.info(
                "generation_wave_started",
                run_id=run_id,
                wave_index=wave.wave_index,
                models=list(wave.models),
            )
            for llm_name in wave.models:
                for phase in self._config.phases:
                    bases: list[str] = (
                        list(self._config.bases) if phase == "A" else [_PHASE_B_BASE]
                    )
                    for base_str in bases:
                        for seed_val in self._config.seeds:
                            for question in questions:
                                row_id = RowId.from_cell(
                                    run_id=run_id,
                                    phase=phase,
                                    base=base_str,
                                    llm=llm_name,
                                    seed=seed_val,
                                    question_id=question.question_id,
                                )
                                if self._writer.exists(row_id):
                                    _log.debug(
                                        "generation_skipped",
                                        run_id=run_id,
                                        wave_index=wave.wave_index,
                                        llm=llm_name,
                                        base=base_str,
                                        seed=seed_val,
                                        question_id=question.question_id,
                                        action="skip",
                                    )
                                    n_skipped += 1
                                else:
                                    result = await self._try_generate(
                                        run_id=run_id,
                                        wave_index=wave.wave_index,
                                        phase=phase,
                                        base_str=base_str,
                                        llm_name=llm_name,
                                        seed_val=seed_val,
                                        question=question,
                                        row_id=row_id,
                                        canonical_contexts=canonical_contexts,
                                    )
                                    if result is None:
                                        n_errors += 1
                                        failed_cells.append(row_id.value)
                                    else:
                                        self._writer.append(result)
                                        n_generated += 1

                                cell_count += 1
                                if cell_count % 10 == 0:
                                    _log.info(
                                        "generation_progress",
                                        run_id=run_id,
                                        wave_index=wave.wave_index,
                                        action="progress",
                                        cell_count=cell_count,
                                        n_generated=n_generated,
                                        n_skipped=n_skipped,
                                        n_errors=n_errors,
                                    )

            _log.info(
                "generation_wave_completed",
                run_id=run_id,
                wave_index=wave.wave_index,
                n_generated=n_generated,
                n_skipped=n_skipped,
                n_errors=n_errors,
            )

        duration_s = time.monotonic() - t_start
        _log.info(
            "generation_pass_completed",
            run_id=run_id,
            n_generated=n_generated,
            n_skipped=n_skipped,
            n_errors=n_errors,
            duration_s=round(duration_s, 3),
            n_failed_cells=len(failed_cells),
        )
        return GenerationPassReport(
            run_id=run_id,
            wave_plan=wave_plan,
            n_generated=n_generated,
            n_skipped=n_skipped,
            n_errors=n_errors,
            duration_s=duration_s,
            failed_cells=tuple(failed_cells),
        )

    async def _try_generate(
        self,
        *,
        run_id: str,
        wave_index: int,
        phase: str,
        base_str: str,
        llm_name: str,
        seed_val: int,
        question: Question,
        row_id: RowId,
        canonical_contexts: dict[str, list[Chunk]] | None,
    ) -> EvaluationResult | None:
        """Tenta gerar uma célula com até ``max_retries`` tentativas de geração.

        A recuperação (Experimento A) é executada uma única vez fora do loop de retry
        — é determinística e o erro esperado é ``GenerationError``, não de retrieval.

        Args:
            run_id: identificador da rodada (logging).
            wave_index: índice da onda corrente (logging).
            phase: fase do experimento (``"A"`` ou ``"B"``).
            base_str: identificador da base de conhecimento.
            llm_name: nome do modelo gerador.
            seed_val: semente de reprodutibilidade.
            question: pergunta a responder.
            row_id: identificador determinístico da célula (ADR-009).
            canonical_contexts: contextos canônicos para o Experimento B.

        Returns:
            :class:`EvaluationResult` em caso de sucesso; ``None`` após max_retries.
        """
        llm = LLMId(llm_name)
        base = BaseId(base_str)
        seed = Seed(seed_val)

        # Recuperação — fora do loop de retry (determinística; sem GenerationError).
        contexts: Sequence[Chunk]
        chunk_ids: tuple[str, ...]
        chunk_texts: tuple[str, ...]
        scores: tuple[float, ...]

        if phase == "A":
            retrieval = await self._retriever.search(
                base=base,
                question=question.text,
                top_k=self._config.retrieval.top_k,
            )
            contexts = retrieval.chunks
            chunk_ids = retrieval.ids
            chunk_texts = tuple(c.text for c in retrieval.chunks)
            scores = retrieval.scores
        else:
            canon = canonical_contexts or {}
            raw = canon.get(question.question_id, [])
            contexts = raw
            chunk_ids = tuple(c.id for c in raw)
            chunk_texts = tuple(c.text for c in raw)
            scores = tuple(c.score for c in raw)

        # Geração com retry em GenerationError.
        for attempt in range(1, self._max_retries + 1):
            try:
                output = await self._generator.generate(
                    llm=llm,
                    question=question.text,
                    contexts=contexts,
                    seed=seed_val,
                    temperature=self._config.temperature,
                )
                answer = GeneratedAnswer(
                    row_id=row_id,
                    question=question,
                    base=base,
                    llm=llm,
                    seed=seed,
                    phase=phase,
                    generated_answer=output.text,
                    retrieved_chunk_ids=chunk_ids,
                    retrieved_chunks_text=chunk_texts,
                    retrieval_scores=scores,
                )
                return EvaluationResult(
                    answer=answer,
                    metrics=_ALL_NAN_METRICS,
                    final_score=FinalScore(_NAN),
                    determinism_regime=DeterminismRegime.GENERATOR,
                    critical_failure_flag=None,
                    critical_failure_note=None,
                    server_mode=self._config.server_mode,
                    served_model_id=self._config.generator_served_model_ids.get(
                        llm_name, ""
                    ),
                    determinism_verified=self._config.judge_determinism_verified,
                )
            except GenerationError as exc:
                is_last = attempt == self._max_retries
                _log.warning(
                    "generation_error",
                    run_id=run_id,
                    wave_index=wave_index,
                    llm=llm_name,
                    base=base_str,
                    seed=seed_val,
                    question_id=question.question_id,
                    action="fail" if is_last else "retry",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=str(exc),
                )
                if is_last:
                    return None
        return None  # satisfaz o type-checker (inalcançável em prática)
