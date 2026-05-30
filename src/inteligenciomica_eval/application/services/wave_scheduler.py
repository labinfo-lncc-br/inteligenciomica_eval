"""WaveSchedulerService — planejamento de ondas de geração (§14.6 TAREFA-303, ADR-012).

Serviço de aplicação **PURO** (python-clean-architecture §2): recebe a especificação dos
modelos e a configuração da rodada e produz um plano de execução (``WavePlan``) — sem I/O,
sem logging, determinístico. NÃO importa de ``infrastructure`` (ADR-001).

ADR-012 (GH200, 4 GPUs): o juiz é residente na GPU 3 e servido à parte; os geradores rodam
nas GPUs 0-2 em **ondas concorrentes** (onda 1: até 3 modelos, um por GPU; onda 2: o resto).
``allow_concurrent_models=False`` serializa (uma onda por modelo) — modo conservador que
**vai contra o ADR-012**, reservado a depuração ou hardware de GPU única.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inteligenciomica_eval.domain.errors import ModelNotInRegistryError
from inteligenciomica_eval.domain.value_objects import ModelWaveSpec

# RF1/§P4: cada rodada usa um conjunto fixo de 13 perguntas curadas (versionado pré-M1).
_RF1_N_QUESTIONS = 13
# ADR-012: juiz na GPU 3 (residente); geradores nas GPUs 0/1/2.
_ADR012_GENERATION_GPUS: tuple[int, ...] = (0, 1, 2)


class RoundConfigView(Protocol):
    """Vista estrutural mínima da configuração de rodada consumida pelo scheduler.

    A camada ``application`` NÃO importa o ``RoundConfig`` Pydantic (que é de
    ``infrastructure`` — import-linter Contract 2/4); depende desta abstração que o
    ``RoundConfig`` satisfaz **estruturalmente** (inversão de dependência, ADR-001). Os
    tipos batem exatamente com os campos do ``RoundConfig`` (§12.1).
    """

    phases: list[str]
    bases: list[str]
    llms: list[str]
    seeds: list[int]


@dataclass(frozen=True, slots=True)
class Wave:
    """Uma onda de geração — modelos que rodam concorrentemente nas GPUs de geração.

    Args:
        wave_index: índice 0-based da onda (ordem estável de execução).
        models: nomes dos modelos nesta onda (ordenados por VRAM desc, depois nome).
        gpu_indices: GPU de geração atribuída a cada modelo (ADR-012; alinhado a ``models``).
        vram_required_gb: soma dos ``vram_gb_awq`` dos modelos da onda.
        cells_in_wave: número de células ``{modelo x seed x pergunta x base}`` da onda.
    """

    wave_index: int
    models: tuple[str, ...]
    gpu_indices: tuple[int, ...]
    vram_required_gb: float
    cells_in_wave: int


@dataclass(frozen=True, slots=True)
class WavePlan:
    """Plano completo de ondas de geração de uma rodada.

    Args:
        waves: ondas em ordem estável de execução.
        total_cells: soma de ``cells_in_wave`` de todas as ondas (células por passada).
        estimated_vram_peak_gb: maior ``vram_required_gb`` entre as ondas (pico concorrente).
    """

    waves: tuple[Wave, ...]
    total_cells: int
    estimated_vram_peak_gb: float


class WaveSchedulerService:
    """Planeja as ondas de geração a partir de ``ModelWaveSpec`` + config de rodada.

    Args:
        allow_concurrent_models: ``True`` (default, ADR-012) agrupa geradores em ondas
            concorrentes (uma GPU por modelo). ``False`` serializa (uma onda por modelo) —
            modo conservador que vai contra o ADR-012 salvo restrição de hardware.
        generation_gpu_indices: GPUs de geração disponíveis (ADR-012 default ``(0, 1, 2)``);
            o tamanho define quantos modelos cabem por onda concorrente.
        n_questions: número de perguntas por célula (RF1 default ``13``); injetável para
            testes determinísticos com golden pequeno.
    """

    def __init__(
        self,
        *,
        allow_concurrent_models: bool = True,
        generation_gpu_indices: tuple[int, ...] = _ADR012_GENERATION_GPUS,
        n_questions: int = _RF1_N_QUESTIONS,
    ) -> None:
        self._allow_concurrent = allow_concurrent_models
        self._generation_gpus = generation_gpu_indices
        self._n_questions = n_questions

    def plan(
        self,
        model_specs: tuple[ModelWaveSpec, ...],
        round_config: RoundConfigView,
    ) -> WavePlan:
        """Produz o :class:`WavePlan` para os geradores listados em ``round_config.llms``.

        Args:
            model_specs: VOs de domínio (TAREFA-301) de todos os modelos do registry.
            round_config: configuração da rodada (vista estrutural, ver
                :class:`RoundConfigView`).

        Returns:
            :class:`WavePlan` com as ondas de geração e os totais.

        Raises:
            ModelNotInRegistryError: se algum ``llm`` de ``round_config.llms`` não tiver
                ``ModelWaveSpec`` correspondente em ``model_specs``.
        """
        by_name = {spec.name: spec for spec in model_specs}
        generators: list[ModelWaveSpec] = []
        for llm in round_config.llms:
            spec = by_name.get(llm)
            if spec is None:
                raise ModelNotInRegistryError(llm)
            if spec.is_judge:
                # ADR-003/012: o juiz é servido à parte (GPU 3), nunca nas ondas de geração.
                continue
            generators.append(spec)

        cells_per_model = self._cells_per_model(round_config)
        # Ordem estável e determinística: VRAM desc (maiores primeiro) e nome como desempate.
        ordered = sorted(generators, key=lambda s: (-s.vram_gb_awq, s.name))

        if self._allow_concurrent:
            waves = self._concurrent_waves(ordered, cells_per_model)
        else:
            waves = self._serial_waves(ordered, cells_per_model)

        total_cells = sum(wave.cells_in_wave for wave in waves)
        peak = max((wave.vram_required_gb for wave in waves), default=0.0)
        return WavePlan(
            waves=tuple(waves),
            total_cells=total_cells,
            estimated_vram_peak_gb=peak,
        )

    def _cells_per_model(self, round_config: RoundConfigView) -> int:
        """Células por modelo somando as fases configuradas (§5.4).

        Experimento A: ``seeds x perguntas x bases``. Experimento B: ``seeds x perguntas``
        (base canônica fixa — §12.1 ``experiment_b``).
        """
        n_seeds = len(round_config.seeds)
        n_bases = len(round_config.bases)
        cells = 0
        if "A" in round_config.phases:
            cells += n_seeds * self._n_questions * n_bases
        if "B" in round_config.phases:
            cells += n_seeds * self._n_questions
        return cells

    def _concurrent_waves(
        self, ordered: list[ModelWaveSpec], cells_per_model: int
    ) -> list[Wave]:
        """Agrupa geradores em ondas de tamanho ``len(generation_gpus)`` (ADR-012)."""
        gpus = self._generation_gpus
        per_wave = len(gpus)
        waves: list[Wave] = []
        for start in range(0, len(ordered), per_wave):
            chunk = ordered[start : start + per_wave]
            waves.append(
                Wave(
                    wave_index=len(waves),
                    models=tuple(spec.name for spec in chunk),
                    gpu_indices=tuple(gpus[: len(chunk)]),
                    vram_required_gb=sum(spec.vram_gb_awq for spec in chunk),
                    cells_in_wave=len(chunk) * cells_per_model,
                )
            )
        return waves

    def _serial_waves(
        self, ordered: list[ModelWaveSpec], cells_per_model: int
    ) -> list[Wave]:
        """Uma onda por modelo (modo serial — contra ADR-012 salvo GPU única)."""
        first_gpu = self._generation_gpus[0] if self._generation_gpus else 0
        return [
            Wave(
                wave_index=index,
                models=(spec.name,),
                gpu_indices=(first_gpu,),
                vram_required_gb=spec.vram_gb_awq,
                cells_in_wave=cells_per_model,
            )
            for index, spec in enumerate(ordered)
        ]
