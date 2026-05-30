from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

import pydantic
import yaml
from pydantic import BaseModel, Field, model_validator

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    ModelNotInRegistryError,
)
from inteligenciomica_eval.domain.value_objects import LLMId, ModelWaveSpec


class ModelEntry(BaseModel):
    """Entrada de configuração de serving de um LLM registrado (§7.2, ADR-012).

    Modelo Pydantic v2 de **infraestrutura pura** (fronteira de config, §5.2). A
    validação cross-field fixa o contrato de regimes determinísticos do ADR-003:
    o juiz roda em ``batch_invariant=True`` com ``tensor_parallel_size=1``; os
    geradores rodam em ``batch_invariant=False`` (produção realista, §9.2.4).

    Args:
        name: identificador do modelo — deve bater com o ``LLMId`` do domínio e
            com as entradas de ``round_config.llms``.
        hf_repo: repositório/caminho HuggingFace do modelo.
        vram_gb_fp16: memória em FP16 (referência teórica), em gigabytes.
        vram_gb_awq: memória de produção (AWQ 4-bit ou regime real), em gigabytes.
        quantization: esquema de quantização do serving.
        tensor_parallel_size: número de GPUs para tensor parallelism (>= 1); deve
            ser ``1`` para o juiz (ADR-003/ADR-012).
        gpu_index: GPU dedicada ao modelo (ADR-012: juiz=3; geradores=0,1,2).
        is_judge: ``True`` somente para o juiz determinístico (Prometheus-2).
        batch_invariant: regime de determinismo; deve ser ``True`` se ``is_judge``
            e ``False`` caso contrário (ADR-003).
        extra_args: flags vLLM adicionais (mapa nome→valor).

    Raises:
        ValueError: se a combinação ``is_judge``/``batch_invariant``/
            ``tensor_parallel_size`` violar o ADR-003 (convertido em
            :class:`ConfigValidationError` por :func:`load_model_registry`).
    """

    name: str
    hf_repo: str
    vram_gb_fp16: Annotated[float, Field(gt=0.0)]
    vram_gb_awq: Annotated[float, Field(gt=0.0)]
    quantization: Literal["awq", "fp16", "fp8", "bfloat16"]
    tensor_parallel_size: Annotated[int, Field(ge=1)]
    gpu_index: Annotated[int, Field(ge=0)]
    is_judge: bool
    batch_invariant: bool
    extra_args: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_regime(self) -> ModelEntry:
        # ADR-003: o regime determinístico do juiz é a garantia de reprodutibilidade
        # científica do subsistema e NÃO pode ser colapsado com o dos geradores.
        if self.is_judge:
            if not self.batch_invariant:
                raise ValueError(
                    f"model {self.name!r}: judge requires batch_invariant=True "
                    "(ADR-003: the judge must be deterministic for reproducible "
                    "scoring)."
                )
            if self.tensor_parallel_size != 1:
                raise ValueError(
                    f"model {self.name!r}: judge requires tensor_parallel_size=1 "
                    "(ADR-003/ADR-012: the judge runs on a single dedicated GPU)."
                )
        elif self.batch_invariant:
            raise ValueError(
                f"model {self.name!r}: generator requires batch_invariant=False "
                "(ADR-003: generators run in the realistic production regime)."
            )
        return self


class GPUSlot(BaseModel):
    """Slot físico de GPU disponível para serving (ADR-012).

    Args:
        gpu_index: índice 0-based da GPU.
        vram_gb: VRAM total da GPU em gigabytes (ex.: ``96.0`` no GH200).
        reserved_gb: headroom reservado para KV-cache e SO; default ``8.0`` GB.
    """

    gpu_index: Annotated[int, Field(ge=0)]
    vram_gb: Annotated[float, Field(gt=0.0)]
    reserved_gb: Annotated[float, Field(ge=0.0)] = 8.0

    @property
    def available_gb(self) -> float:
        """VRAM utilizável para o modelo = ``vram_gb - reserved_gb``.

        Returns:
            Gigabytes disponíveis após o headroom reservado.
        """
        return self.vram_gb - self.reserved_gb


class ModelRegistryConfig(BaseModel):
    """Catálogo de modelos + layout de GPUs de uma rodada (§7.2, ADR-012).

    Modelo Pydantic v2 de infraestrutura, carregado de ``config/model_registry.yaml``
    — arquivo SEPARADO do YAML de rodada (§8/§12.1). As validações de conjunto
    (unicidade, juiz único, capacidade de VRAM por GPU) rodam na carga (fail-fast).

    Args:
        models: lista de entradas de modelo (geradores + exatamente um juiz).
        gpu_slots: lista de slots de GPU disponíveis.

    Raises:
        ValueError: em nomes duplicados, número de juízes != 1, ``gpu_index`` sem
            slot correspondente, ou ``vram_gb_awq`` excedendo o ``available_gb`` da
            GPU alvo (convertido em :class:`ConfigValidationError` por
            :func:`load_model_registry`).
    """

    models: list[ModelEntry]
    gpu_slots: list[GPUSlot]

    @model_validator(mode="after")
    def _validate_registry(self) -> ModelRegistryConfig:
        names = [m.name for m in self.models]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"duplicate model names in registry: {duplicates!r}")

        judges = [m.name for m in self.models if m.is_judge]
        if len(judges) != 1:
            raise ValueError(
                f"registry must contain exactly one judge (is_judge=True); "
                f"found {len(judges)}: {judges!r} (ADR-003)."
            )

        slots_by_index: dict[int, GPUSlot] = {s.gpu_index: s for s in self.gpu_slots}
        if len(slots_by_index) != len(self.gpu_slots):
            raise ValueError("duplicate gpu_index values in gpu_slots")

        for model in self.models:
            slot = slots_by_index.get(model.gpu_index)
            if slot is None:
                raise ValueError(
                    f"model {model.name!r} targets gpu_index={model.gpu_index} "
                    "which has no matching GPUSlot."
                )
            if model.vram_gb_awq > slot.available_gb:
                raise ValueError(
                    f"model {model.name!r} needs {model.vram_gb_awq} GB (AWQ) but "
                    f"gpu_index={model.gpu_index} only has {slot.available_gb} GB "
                    f"available (vram_gb={slot.vram_gb} - "
                    f"reserved_gb={slot.reserved_gb})."
                )
        return self


def get_model(registry: ModelRegistryConfig, llm_id: LLMId) -> ModelEntry:
    """Resolve uma entrada de modelo pelo ``LLMId`` do domínio.

    Args:
        registry: catálogo de modelos carregado.
        llm_id: identificador de domínio do modelo procurado.

    Returns:
        A :class:`ModelEntry` cujo ``name`` bate com ``llm_id.value``.

    Raises:
        ModelNotInRegistryError: se nenhum modelo registrado tiver esse nome.
    """
    for model in registry.models:
        if model.name == llm_id.value:
            return model
    raise ModelNotInRegistryError(llm_id.value)


def to_wave_spec(entry: ModelEntry) -> ModelWaveSpec:
    """Extrai o VO de domínio :class:`ModelWaveSpec` de um :class:`ModelEntry` (infra).

    Ponto canônico de extração (Nota M3 item 5) — usado pelo CLI ``--dry-run`` (TAREFA-303)
    e pelo wiring (TAREFA-309) para alimentar o ``WaveSchedulerService`` (application) sem
    expor tipos de infraestrutura à camada de aplicação.

    Args:
        entry: entrada de modelo do registry.

    Returns:
        :class:`ModelWaveSpec` com os campos de serving/GPU relevantes ao scheduler.
    """
    return ModelWaveSpec(
        name=entry.name,
        vram_gb_awq=entry.vram_gb_awq,
        is_judge=entry.is_judge,
        tensor_parallel_size=entry.tensor_parallel_size,
        quantization=entry.quantization,
        gpu_index=entry.gpu_index,
        extra_args=dict(entry.extra_args),
    )


def load_model_registry(path: Path) -> ModelRegistryConfig:
    """Carrega e valida o registry de modelos a partir de um YAML (fail-fast, §14.2).

    Converte qualquer ``pydantic.ValidationError`` em :class:`ConfigValidationError`
    apontando o primeiro campo falho — mesmo padrão de ``load_round_config`` (§3).

    Args:
        path: caminho do arquivo YAML do registry.

    Returns:
        Instância validada de :class:`ModelRegistryConfig`.

    Raises:
        ConfigValidationError: se o YAML falhar na validação de esquema ou regras.
        FileNotFoundError: se ``path`` não existir.
    """
    # yaml.safe_load returns Any; Pydantic validates immediately after.
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigValidationError("(root)", "YAML must be a mapping at top level")
    try:
        return ModelRegistryConfig.model_validate(raw)
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(loc) for loc in first["loc"])
        reason = first["msg"]
        raise ConfigValidationError(field, reason) from exc
