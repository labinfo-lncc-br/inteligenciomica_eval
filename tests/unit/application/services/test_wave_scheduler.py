from __future__ import annotations

from dataclasses import dataclass

import pytest

from inteligenciomica_eval.application.services.wave_scheduler import (
    Wave,
    WavePlan,
    WaveSchedulerService,
)
from inteligenciomica_eval.domain.errors import ModelNotInRegistryError
from inteligenciomica_eval.domain.value_objects import ModelWaveSpec

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _gen(name: str, *, vram: float = 80.0, gpu: int = 0) -> ModelWaveSpec:
    return ModelWaveSpec(
        name=name,
        vram_gb_awq=vram,
        is_judge=False,
        tensor_parallel_size=1,
        quantization="awq",
        gpu_index=gpu,
        extra_args={},
    )


def _judge(name: str = "judge") -> ModelWaveSpec:
    return ModelWaveSpec(
        name=name,
        vram_gb_awq=26.0,
        is_judge=True,
        tensor_parallel_size=1,
        quantization="awq",
        gpu_index=3,
        extra_args={},
    )


@dataclass
class _Round:
    """Stand-in estrutural de RoundConfigView (duck-typing — ver wave_scheduler)."""

    llms: list[str]
    seeds: list[int]
    bases: list[str]
    phases: list[str]


def _round(
    llms: list[str],
    *,
    seeds: list[int] | None = None,
    bases: list[str] | None = None,
    phases: list[str] | None = None,
) -> _Round:
    return _Round(
        llms=llms,
        seeds=seeds if seeds is not None else [42, 99],
        bases=bases if bases is not None else ["IDx_400k"],
        phases=phases if phases is not None else ["A"],
    )


# ---------------------------------------------------------------------------
# Concurrent (default ADR-012)
# ---------------------------------------------------------------------------


def test_concurrent_three_then_two() -> None:
    specs = tuple(_gen(f"gen-{i}", vram=float(50 - i)) for i in range(5))
    names = [s.name for s in specs]
    plan = WaveSchedulerService().plan(specs, _round(names))
    assert len(plan.waves) == 2
    assert len(plan.waves[0].models) == 3
    assert plan.waves[0].gpu_indices == (0, 1, 2)
    assert len(plan.waves[1].models) == 2
    assert plan.waves[1].gpu_indices == (0, 1)


def test_concurrent_orders_by_vram_desc() -> None:
    specs = (
        _gen("small", vram=10.0),
        _gen("big", vram=90.0),
        _gen("mid", vram=50.0),
    )
    plan = WaveSchedulerService().plan(specs, _round(["small", "big", "mid"]))
    # Onda única (3 GPUs), ordenada por VRAM desc: big, mid, small.
    assert plan.waves[0].models == ("big", "mid", "small")


def test_concurrent_is_default() -> None:
    assert WaveSchedulerService()._allow_concurrent is True


# ---------------------------------------------------------------------------
# Serial (contra ADR-012)
# ---------------------------------------------------------------------------


def test_serial_one_wave_per_model() -> None:
    specs = tuple(_gen(f"gen-{i}") for i in range(5))
    names = [s.name for s in specs]
    plan = WaveSchedulerService(allow_concurrent_models=False).plan(
        specs, _round(names)
    )
    assert len(plan.waves) == 5
    assert all(len(w.models) == 1 for w in plan.waves)
    assert all(w.gpu_indices == (0,) for w in plan.waves)


# ---------------------------------------------------------------------------
# Filtragem / juiz / erros
# ---------------------------------------------------------------------------


def test_missing_llm_raises_model_not_in_registry() -> None:
    specs = (_gen("gen-a"), _judge())
    with pytest.raises(ModelNotInRegistryError):
        WaveSchedulerService().plan(specs, _round(["gen-a", "ghost"]))


def test_judge_never_in_generation_waves() -> None:
    specs = (_gen("gen-a"), _gen("gen-b"), _judge("the-judge"))
    plan = WaveSchedulerService().plan(specs, _round(["gen-a", "gen-b"]))
    all_models = {m for w in plan.waves for m in w.models}
    assert "the-judge" not in all_models


def test_judge_excluded_even_if_listed_in_llms() -> None:
    specs = (_gen("gen-a"), _judge("the-judge"))
    plan = WaveSchedulerService().plan(specs, _round(["gen-a", "the-judge"]))
    all_models = {m for w in plan.waves for m in w.models}
    assert all_models == {"gen-a"}


def test_empty_generators_yields_empty_plan() -> None:
    plan = WaveSchedulerService().plan((_judge(),), _round([]))
    assert plan.waves == ()
    assert plan.total_cells == 0
    assert plan.estimated_vram_peak_gb == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# cells_in_wave / total / VRAM (golden)
# ---------------------------------------------------------------------------


def test_cells_in_wave_golden_phase_a() -> None:
    # n_questions=2, seeds=[1,2] (2), bases=["b1"] (1), phase A => 2*2*1 = 4 por modelo.
    specs = (_gen("m1"), _gen("m2"), _gen("m3"))
    plan = WaveSchedulerService(n_questions=2).plan(
        specs, _round(["m1", "m2", "m3"], seeds=[1, 2], bases=["b1"], phases=["A"])
    )
    assert plan.waves[0].cells_in_wave == 12  # 3 modelos x 4
    assert plan.total_cells == 12


def test_cells_in_wave_golden_phase_a_and_b() -> None:
    # A: 2*2*1=4 ; B: 2*2=4 (base fixa) => 8 por modelo.
    specs = (_gen("m1"), _gen("m2"))
    plan = WaveSchedulerService(n_questions=2).plan(
        specs,
        _round(["m1", "m2"], seeds=[1, 2], bases=["b1"], phases=["A", "B"]),
    )
    assert plan.waves[0].cells_in_wave == 16  # 2 modelos x 8
    assert plan.total_cells == 16


def test_phase_b_ignores_base_count() -> None:
    # B só: n_questions=2, seeds=[1,2], 3 bases => base fixa => 2*2 = 4 por modelo.
    specs = (_gen("m1"),)
    plan = WaveSchedulerService(n_questions=2).plan(
        specs, _round(["m1"], seeds=[1, 2], bases=["b1", "b2", "b3"], phases=["B"])
    )
    assert plan.waves[0].cells_in_wave == 4


def test_vram_required_and_peak() -> None:
    specs = (
        _gen("a", vram=50.0),
        _gen("b", vram=40.0),
        _gen("c", vram=30.0),
        _gen("d", vram=20.0),
    )
    plan = WaveSchedulerService().plan(specs, _round(["a", "b", "c", "d"]))
    # Onda 0: a+b+c = 120 ; Onda 1: d = 20. Peak = 120.
    assert plan.waves[0].vram_required_gb == pytest.approx(120.0)
    assert plan.waves[1].vram_required_gb == pytest.approx(20.0)
    assert plan.estimated_vram_peak_gb == pytest.approx(120.0)


def test_default_n_questions_is_rf1_thirteen() -> None:
    specs = (_gen("m1"),)
    plan = WaveSchedulerService().plan(
        specs, _round(["m1"], seeds=[42], bases=["b1"], phases=["A"])
    )
    assert plan.waves[0].cells_in_wave == 13  # 1 seed x 13 perguntas x 1 base


# ---------------------------------------------------------------------------
# DTOs / determinismo
# ---------------------------------------------------------------------------


def test_dtos_are_frozen() -> None:
    wave = Wave(
        wave_index=0,
        models=("m1",),
        gpu_indices=(0,),
        vram_required_gb=10.0,
        cells_in_wave=1,
    )
    plan = WavePlan(waves=(wave,), total_cells=1, estimated_vram_peak_gb=10.0)
    with pytest.raises(AttributeError):
        wave.wave_index = 1  # type: ignore[misc]
    with pytest.raises(AttributeError):
        plan.total_cells = 2  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    specs = tuple(_gen(f"gen-{i}", vram=float(i)) for i in range(5))
    names = [s.name for s in specs]
    svc = WaveSchedulerService()
    assert svc.plan(specs, _round(names)) == svc.plan(specs, _round(names))


def test_gpu_indices_aligned_with_models() -> None:
    specs = tuple(_gen(f"gen-{i}") for i in range(5))
    plan = WaveSchedulerService().plan(specs, _round([s.name for s in specs]))
    for wave in plan.waves:
        assert len(wave.gpu_indices) == len(wave.models)
