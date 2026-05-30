from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from enum import Enum

from inteligenciomica_eval.domain.errors import (
    InteligenciomicaEvalError,
    InvalidBaseIdError,
    InvalidLLMIdError,
    InvalidSeedError,
    ScoreOutOfRangeError,
)

_VALID_BASE_IDS: frozenset[str] = frozenset({"IDx_400k", "ID_230K", "fixed"})
_SHA256_HEX_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{64}$")


class DeterminismRegime(Enum):
    """Regime de determinismo da avaliação (§4.1).

    Valores serializados em minúsculas conforme contrato arquitetural (§4.1, tabela).
    """

    JUDGE = "judge"
    GENERATOR = "generator"


@dataclass(frozen=True, slots=True)
class BaseId:
    """Identificador da base de conhecimento.

    Valores aceitos: ``"IDx_400k"``, ``"ID_230K"``, ``"fixed"``.
    O valor ``"fixed"`` é reservado ao Experimento B (§5.3).

    Args:
        value: string identificadora da base.

    Raises:
        InvalidBaseIdError: se o valor não pertencer ao conjunto aceito.
    """

    value: str

    def __post_init__(self) -> None:
        if self.value not in _VALID_BASE_IDS:
            raise InvalidBaseIdError(self.value)


@dataclass(frozen=True, slots=True)
class LLMId:
    """Identificador de modelo LLM — string não-vazia e sem espaços.

    A pertinência ao registry é validada em ``ModelNotInRegistryError`` na
    carga de configuração, não aqui. Este VO valida apenas o formato.

    Args:
        value: identificador do modelo.

    Raises:
        InvalidLLMIdError: se o valor for vazio ou contiver espaços.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or " " in self.value:
            raise InvalidLLMIdError(self.value)


@dataclass(frozen=True, slots=True)
class Seed:
    """Semente de reprodutibilidade para geração/avaliação.

    Args:
        value: inteiro não-negativo (>= 0).

    Raises:
        InvalidSeedError: se o valor for negativo.
    """

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise InvalidSeedError(self.value)


@dataclass(frozen=True, slots=True)
class FinalScore:
    """Score final agregado de uma resposta.

    Aceita valores em ``[0.0, 1.0]`` ou ``NaN`` (métrica não computável).

    Args:
        value: score numérico.

    Raises:
        ScoreOutOfRangeError: se não-NaN e fora de [0.0, 1.0].
    """

    value: float

    def __post_init__(self) -> None:
        if not math.isnan(self.value) and not (0.0 <= self.value <= 1.0):
            raise ScoreOutOfRangeError(self.value, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class RankScore:
    """Score de ranking — pode ser negativo (penalização clínica, §7.3) ou NaN.

    Aceita qualquer ``float`` finito ou NaN (inclusive negativos). Rejeita
    ±inf e qualquer tipo que não seja ``float`` (ex.: ``int``, ``str``).

    Args:
        value: score de ranking; deve ser ``float``.

    Raises:
        InteligenciomicaEvalError: se o valor não for ``float``, ou for ±inf.
    """

    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.value, float):  # rejeita int, str, bool, None …
            raise InteligenciomicaEvalError(
                f"RankScore.value must be a float, got {type(self.value).__name__!r}"
            )
        if math.isinf(self.value):
            raise InteligenciomicaEvalError(
                f"RankScore must be a finite float or NaN, got: {self.value!r}"
            )


@dataclass(frozen=True, slots=True)
class MetricVector:
    """Container imutável das métricas de Camada 1+2 de uma resposta.

    Cada campo pode ser ``NaN`` quando a métrica não foi computada.

    Args:
        answer_correctness: exatidão da resposta gerada.
        answer_similarity: similaridade semântica com a referência.
        faithfulness: fidelidade da resposta ao contexto recuperado.
        context_precision: precisão dos chunks recuperados.
        context_recall: cobertura dos chunks relevantes.
        answer_relevancy: relevância da resposta para a pergunta.
        bertscore_f1: F1 do BERTScore.
        rubric_biomed_score: score de rubrica biomédica (juiz LLM).
    """

    answer_correctness: float
    answer_similarity: float
    faithfulness: float
    context_precision: float
    context_recall: float
    answer_relevancy: float
    bertscore_f1: float
    rubric_biomed_score: float

    def nan_fields(self) -> tuple[str, ...]:
        """Retorna os nomes dos campos cujo valor é NaN.

        Alimenta o campo ``metric_nan_fields`` no schema de saída (ADR-007).

        Returns:
            Tupla ordenada com os nomes dos campos NaN (pode ser vazia).
        """
        result: list[str] = []
        checks: list[tuple[str, float]] = [
            ("answer_correctness", self.answer_correctness),
            ("answer_similarity", self.answer_similarity),
            ("faithfulness", self.faithfulness),
            ("context_precision", self.context_precision),
            ("context_recall", self.context_recall),
            ("answer_relevancy", self.answer_relevancy),
            ("bertscore_f1", self.bertscore_f1),
            ("rubric_biomed_score", self.rubric_biomed_score),
        ]
        for name, val in checks:
            if math.isnan(val):
                result.append(name)
        return tuple(result)


@dataclass(frozen=True, slots=True)
class RowId:
    """Identificador de linha determinístico — digest SHA-256 em hexadecimal (ADR-009).

    O construtor espera um digest de 64 caracteres hexadecimais minúsculos,
    como produzido por :meth:`from_cell`. Use :meth:`from_cell` como factory
    primária; o construtor direto é para hidratação a partir de armazenamento.

    Args:
        value: string hexadecimal de 64 caracteres (SHA-256).

    Raises:
        ValueError: se ``value`` não for um digest SHA-256 hex minúsculo válido.
    """

    value: str

    def __post_init__(self) -> None:
        if not _SHA256_HEX_RE.match(self.value):
            raise ValueError(
                f"RowId must be a 64-char lowercase hex SHA-256 digest, got: {self.value!r}"
            )

    @classmethod
    def from_cell(
        cls,
        *,
        run_id: str,
        phase: str,
        base: str,
        llm: str,
        seed: int,
        question_id: str,
    ) -> RowId:
        """Computa o RowId determinístico a partir dos componentes da célula.

        Serializa os componentes com separador ``|`` (suficiente para os
        identificadores controlados do domínio) e aplica SHA-256.

        Args:
            run_id: identificador do run de avaliação.
            phase: fase do experimento (ex: ``"eval"``).
            base: identificador da base de conhecimento.
            llm: identificador do modelo LLM.
            seed: semente de reprodutibilidade.
            question_id: identificador da questão.

        Returns:
            :class:`RowId` com o digest SHA-256 dos componentes.
        """
        payload = "|".join([run_id, phase, base, llm, str(seed), question_id])
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return cls(value=digest)


@dataclass(frozen=True, slots=True)
class ModelWaveSpec:
    """Especificação de serving/GPU de um modelo para a camada de aplicação.

    VO de domínio puro (Nota de operacionalização M3 item 5, TAREFA-301).
    Abstrai os dados de GPU do ``ModelEntry`` de infraestrutura para que o
    ``WaveSchedulerService`` (application, TAREFA-303) planeje as ondas sem
    importar de ``infrastructure`` (ADR-001). Construído pelo wiring (TAREFA-309)
    a partir de cada ``ModelEntry``.

    Args:
        name: identificador do modelo (deve bater com ``LLMId``/round config).
        vram_gb_awq: VRAM de produção (AWQ 4-bit ou regime real), em gigabytes.
        is_judge: ``True`` apenas para o juiz determinístico (Prometheus-2).
        tensor_parallel_size: número de GPUs para tensor parallelism (>= 1).
        quantization: esquema de quantização (ex.: ``"awq"``, ``"bfloat16"``).
        gpu_index: GPU dedicada (ADR-012: juiz=3; geradores=0,1,2).
        extra_args: flags vLLM adicionais (mapa nome→valor).
    """

    name: str
    vram_gb_awq: float
    is_judge: bool
    tensor_parallel_size: int
    quantization: str
    gpu_index: int
    extra_args: dict[str, str]
