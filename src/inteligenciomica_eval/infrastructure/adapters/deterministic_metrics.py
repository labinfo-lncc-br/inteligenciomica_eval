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
- **``rouge_l`` é campo de log, não de schema** (Nota M1 item 10): o ``ParquetStorage``
  (§5.3) persiste apenas ``bertscore_f1``; ``rouge_l`` é registrado via structlog
  em ``deterministic_metrics_computed`` para sanity check.
- **NaN absorvido** (DoD §14.2): falhas de cálculo viram ``float("nan")`` por campo e
  são logadas em WARNING; o adapter nunca propaga exceção para o caller.
"""

from __future__ import annotations

import functools
import time
from typing import Any

import bert_score
import structlog
from rouge_score import rouge_scorer

from inteligenciomica_eval.domain.ports import AuxMetrics

_log = structlog.get_logger(__name__)

_DEFAULT_LANG = "pt"
_DEFAULT_DEVICE = "cpu"


class DeterministicMetricsAdapter:
    """Calcula BERTScore-F1 e ROUGE-L para um par ``(answer, ground_truth)``.

    Os textos são português biomédico; ``lang="pt"`` faz o BERTScore usar o modelo
    ``bert-base-multilingual-cased`` (§5.2). Ambos os clientes internos são
    *lazy-loaded* via :func:`functools.cached_property`, para não atrasar o startup
    do processo — o modelo BERT é carregado **uma única vez** por adapter, na primeira
    chamada a :meth:`score`, e reutilizado nas chamadas seguintes.

    Args:
        lang: idioma passado ao BERTScore (padrão ``"pt"``).
        rescale_with_baseline: reescala os scores do BERTScore pelo baseline do
            idioma (padrão ``True``), tornando a faixa mais interpretável.
        device: dispositivo do BERTScore (padrão ``"cpu"``) — fixado para impedir
            uso acidental de GPU em ambientes CUDA (§5.2, adapter CPU-bound).
    """

    def __init__(
        self,
        *,
        lang: str = _DEFAULT_LANG,
        rescale_with_baseline: bool = True,
        device: str = _DEFAULT_DEVICE,
    ) -> None:
        self._lang = lang
        self._rescale_with_baseline = rescale_with_baseline
        self._device = device

    # ------------------------------------------------------------------
    # Clientes internos — lazy-load via cached_property (§ spec TAREFA-018)
    # ------------------------------------------------------------------

    @functools.cached_property
    def _bert_scorer(self) -> Any:
        """Instancia o ``BERTScorer`` (modelo carregado uma única vez) sob demanda.

        Usar a **classe** ``bert_score.BERTScorer`` — e não a API funcional
        ``bert_score.score`` — é o que garante **carga única** do modelo BERT
        multilíngue: a classe carrega os pesos no ``__init__`` e os mantém em memória,
        enquanto ``bert_score.score`` recarregaria o modelo a cada chamada. O
        ``cached_property`` garante que esse ``__init__`` rode uma só vez por adapter,
        mantendo o ponto de carga fora do ``__init__`` do próprio adapter. ``device``
        é fixado (padrão ``"cpu"``) para impedir uso acidental de GPU.

        Returns:
            :class:`bert_score.BERTScorer`. Tipado como ``Any`` porque ``bert_score``
            não fornece stubs de tipo.
        """
        return bert_score.BERTScorer(
            lang=self._lang,
            rescale_with_baseline=self._rescale_with_baseline,
            device=self._device,
        )

    @functools.cached_property
    def _rouge_scorer(self) -> Any:
        """Instancia o ``RougeScorer`` (rougeL, sem stemmer) sob demanda.

        Returns:
            :class:`rouge_score.rouge_scorer.RougeScorer`. Tipado como ``Any``
            porque ``rouge_score`` não fornece stubs de tipo.
        """
        return rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)

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
            _, _, f1 = self._bert_scorer.score([answer], [ground_truth])
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
            scores = self._rouge_scorer.score(ground_truth, answer)
            return float(scores["rougeL"].fmeasure)
        except Exception as exc:
            _log.warning(
                "rouge_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return float("nan")
