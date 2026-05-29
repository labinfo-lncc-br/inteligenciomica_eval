"""DeterministicMetricsAdapter — métricas auxiliares de Camada 1 sem LLM (§5.2).

Implementa ``DeterministicMetricPort`` calculando BERTScore-F1 e ROUGE-L — ambas
determinísticas, CPU-bound, sem chamada de rede e sem LLM (*sanity check*, §13.3).

Notas de design:

- **Síncrono** (Nota M1 item 1): adapters determinísticos por natureza não são
  promovidos a ``async`` — não há I/O de rede a sobrepor.
- **``batch_invariant`` é irrelevante** aqui: não há LLM nem GPU envolvidos, portanto
  o determinismo não depende do regime BATCH_INVARIANT (ADR-003). O resultado é
  função pura do par ``(answer, ground_truth)``.
- **Carga única do modelo + CPU fixo**: usa ``bert_score.BERTScorer`` (classe, que
  retém os pesos em memória) em vez da API funcional ``bert_score.score`` (que
  recarregaria o modelo a cada chamada); ``device="cpu"`` impede uso acidental de GPU
  em ambientes CUDA — o adapter é CPU-bound por design (§5.2).
- **Lazy init por atributo de instância, NÃO ``cached_property``** (Nota M2 item 2,
  TAREFA-025): o modelo é carregado na primeira chamada a :meth:`score` via
  :meth:`_get_scorer`, que cacheia a instância em ``self._scorer``. Ver a docstring de
  :meth:`_get_scorer` para o porquê de não usar ``functools.cached_property``.
- **``rouge_l`` é campo de log, não de schema** (Nota M1 item 10): o ``ParquetStorage``
  (§5.3) persiste apenas ``bertscore_f1``; ``rouge_l`` é registrado via structlog
  em ``deterministic_metrics_computed`` para sanity check.
- **NaN absorvido** (DoD §14.2): falhas de cálculo viram ``float("nan")`` por campo e
  são logadas em WARNING; o adapter nunca propaga exceção para o caller.
"""

from __future__ import annotations

import time
from typing import Any

import bert_score
import structlog
from rouge_score import rouge_scorer

from inteligenciomica_eval.domain.ports import AuxMetrics
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    DeterministicAdapterConfig,
)

_log = structlog.get_logger(__name__)


class DeterministicMetricsAdapter:
    """Calcula BERTScore-F1 e ROUGE-L para um par ``(answer, ground_truth)``.

    Os textos são português biomédico; ``lang="pt"`` (da config) faz o BERTScore usar o
    modelo ``bert-base-multilingual-cased`` (§5.2). Ambos os scorers internos são
    *lazy-loaded* via atributo de instância (``self._scorer`` / ``self._rouge``), não
    via ``functools.cached_property`` — ver :meth:`_get_scorer`. O modelo BERT é
    carregado **uma única vez** por adapter, na primeira chamada a :meth:`score`, e
    reutilizado nas chamadas seguintes.

    Args:
        config: :class:`DeterministicAdapterConfig` com ``model_type``, ``lang``,
            ``rescale_with_baseline`` e ``device``. ``None`` ⇒ defaults canônicos
            (``lang="pt"`` etc.) — ``DeterministicMetricsAdapter()`` é equivalente a
            ``DeterministicMetricsAdapter(DeterministicAdapterConfig())``.
    """

    def __init__(self, config: DeterministicAdapterConfig | None = None) -> None:
        self._config = config or DeterministicAdapterConfig()
        # Lazy init por atributo de instância (NÃO cached_property — Nota M2 item 2).
        self._scorer: bert_score.BERTScorer | None = None
        self._rouge: rouge_scorer.RougeScorer | None = None

    # ------------------------------------------------------------------
    # Scorers internos — lazy-load por atributo de instância (TAREFA-025)
    # ------------------------------------------------------------------

    def _get_scorer(self) -> Any:
        """Instancia o ``BERTScorer`` sob demanda e o cacheia em ``self._scorer``.

        Usa a **classe** ``bert_score.BERTScorer`` (e não a API funcional
        ``bert_score.score``) para garantir **carga única** do modelo: a classe retém
        os pesos em memória, enquanto ``bert_score.score`` recarregaria o modelo a cada
        chamada. O cache é um **atributo de instância** (``self._scorer``), não um
        ``functools.cached_property``: ``cached_property`` materializa o valor no
        ``__dict__`` da instância, mas seu descritor é compartilhado pela **classe** —
        em suítes de teste isso facilita vazamento de estado mockado entre instâncias e
        dificulta o isolamento. Um atributo de instância simples mantém cada adapter com
        o seu próprio scorer (duas instâncias distintas têm ``_scorer`` distintos).

        Returns:
            :class:`bert_score.BERTScorer`. Tipado como ``Any`` porque ``bert_score``
            não fornece stubs de tipo.
        """
        if self._scorer is None:
            self._scorer = bert_score.BERTScorer(
                model_type=self._config.model_type,
                lang=self._config.lang,
                rescale_with_baseline=self._config.rescale_with_baseline,
                device=self._config.device,
            )
        return self._scorer

    def _get_rouge(self) -> Any:
        """Instancia o ``RougeScorer`` (rougeL, sem stemmer) sob demanda e o cacheia.

        Returns:
            :class:`rouge_score.rouge_scorer.RougeScorer`. Tipado como ``Any`` porque
            ``rouge_score`` não fornece stubs de tipo.
        """
        if self._rouge is None:
            self._rouge = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)
        return self._rouge

    # ------------------------------------------------------------------
    # DeterministicMetricPort interface
    # ------------------------------------------------------------------

    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        """Calcula as métricas auxiliares determinísticas para um par.

        Args:
            answer: texto da resposta gerada pelo LLM sob avaliação.
            ground_truth: resposta de referência humana.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.AuxMetrics` com
            ``bertscore_f1`` e ``rouge_l``; cada campo pode ser ``float("nan")``
            em caso de falha de cálculo (nunca levanta exceção — DoD §14.2).
        """
        t0 = time.monotonic()
        bertscore_f1 = self._compute_bertscore(answer, ground_truth)
        rouge_l = self._compute_rouge_l(answer, ground_truth)
        latency_ms = int((time.monotonic() - t0) * 1000)

        _log.info(
            "deterministic_metrics_computed",
            bertscore_f1=bertscore_f1,
            rouge_l=rouge_l,
            latency_ms=latency_ms,
        )

        return AuxMetrics(bertscore_f1=bertscore_f1, rouge_l=rouge_l)

    # ------------------------------------------------------------------
    # Cálculo interno — cada métrica absorve sua própria falha (NaN por campo)
    # ------------------------------------------------------------------

    def _compute_bertscore(self, answer: str, ground_truth: str) -> float:
        """Calcula o BERTScore-F1; retorna ``float("nan")`` em qualquer falha.

        ``BERTScorer.score(cands, refs)``: o ``answer`` é a *candidate* (hipótese) e
        o ``ground_truth`` é a *reference*.
        """
        try:
            _, _, f1 = self._get_scorer().score([answer], [ground_truth])
            return float(f1.mean().item())
        except Exception as exc:
            _log.warning(
                "bertscore_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return float("nan")

    def _compute_rouge_l(self, answer: str, ground_truth: str) -> float:
        """Calcula o ROUGE-L F-measure; retorna ``float("nan")`` em qualquer falha.

        ``RougeScorer.score(target, prediction)``: o ``ground_truth`` é o *target*
        (referência) e o ``answer`` é a *prediction* (hipótese).
        """
        try:
            scores = self._get_rouge().score(ground_truth, answer)
            return float(scores["rougeL"].fmeasure)
        except Exception as exc:
            _log.warning(
                "rouge_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return float("nan")
