from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from factories.factories import (
    make_config_aggregate,
    make_evaluation_result,
    make_generated_answer,
    make_row_id,
)
from fakes.storage import InMemoryResultReader, InMemoryResultStore, InMemoryResultWriter

from inteligenciomica_eval.application.aggregate_results import (
    AggregateResultsInput,
    AggregateResultsOutput,
    AggregateResultsUseCase,
)
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.services.aggregation import AggregationService
from inteligenciomica_eval.domain.services.rank_score import RankScoreCalculator
from inteligenciomica_eval.domain.value_objects import (
    FinalScore,
    RankScore,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_RUN_ID = "run-001"
_ROUND_ID = "round_1"


def _make_mock_agg(base: str, llm: str, rank: float, n_excl: int = 0) -> MagicMock:
    """Build a MagicMock that quacks like ConfigAggregate with a given rank_score."""
    agg = make_config_aggregate(
        base=base,
        llm=llm,
        rank_score=rank,
        n_excluded_nan=n_excl,
    )
    return agg


def _make_use_case(
    reader: object,
    agg_service: AggregationService,
    data_dir: Path,
) -> AggregateResultsUseCase:
    return AggregateResultsUseCase(
        reader=reader,  # type: ignore[arg-type]
        aggregation_service=agg_service,
        data_dir=data_dir,
    )


def _mock_reader(results: tuple) -> MagicMock:
    """Create a reader mock that returns a ResultFrame with the given results."""
    reader = MagicMock()
    reader.load.return_value = ResultFrame(results=results)
    return reader


def _mock_aggregation_service(aggregates: tuple) -> MagicMock:
    """Create an AggregationService mock returning the given aggregates."""
    svc = MagicMock(spec=AggregationService)
    svc.aggregate_all.return_value = aggregates
    return svc


# ---------------------------------------------------------------------------
# a) 2 configs × 3 perguntas × 2 seeds = 12 resultados — agregados corretos
# ---------------------------------------------------------------------------


def test_aggregate_returns_correct_output(tmp_path: Path) -> None:
    agg_a = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.75, n_excl=1)
    agg_b = _make_mock_agg("ID_230K", "mistral-7b", rank=0.25, n_excl=0)

    results: tuple = tuple(
        make_evaluation_result(
            answer=make_generated_answer(
                base=base,
                llm=llm,
                seed=seed,
                question_id=qid,
            )
        )
        for base, llm in [("IDx_400k", "llama3-8b"), ("ID_230K", "mistral-7b")]
        for qid in ["q01", "q02", "q03"]
        for seed in [42, 43]
    )

    reader = _mock_reader(results)
    svc = _mock_aggregation_service((agg_a, agg_b))

    uc = _make_use_case(reader, svc, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    assert isinstance(out, AggregateResultsOutput)
    assert out.run_id == _RUN_ID
    assert out.round_id == _ROUND_ID
    assert out.n_total_results == 12
    assert out.n_configs == 2


# ---------------------------------------------------------------------------
# b) best_config é a config com maior rank_score — testado
# ---------------------------------------------------------------------------


def test_best_config_is_highest_rank_score(tmp_path: Path) -> None:
    agg_low = _make_mock_agg("ID_230K", "mistral-7b", rank=0.25)
    agg_high = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.75)

    reader = _mock_reader(tuple())
    # AggregationService retorna os agregados em ordem arbitrária (baixo primeiro)
    svc = _mock_aggregation_service((agg_low, agg_high))

    uc = _make_use_case(reader, svc, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    assert out.best_config == agg_high
    assert out.best_config.rank_score.value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# c) NaN excluído: n_nan_excluded correto — testado
# ---------------------------------------------------------------------------


def test_n_nan_excluded_is_sum_of_all_configs(tmp_path: Path) -> None:
    agg_a = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.75, n_excl=1)
    agg_b = _make_mock_agg("ID_230K", "mistral-7b", rank=0.25, n_excl=2)

    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((agg_a, agg_b))

    uc = _make_use_case(reader, svc, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    assert out.n_nan_excluded == 3  # 1 + 2


# ---------------------------------------------------------------------------
# d) Ordenação desc por rank_score — testado
# ---------------------------------------------------------------------------


def test_aggregates_ordered_descending_by_rank_score(tmp_path: Path) -> None:
    agg_mid = _make_mock_agg("ID_230K", "mistral-7b", rank=0.50)
    agg_high = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.75)
    agg_low = _make_mock_agg("ID_230K", "mistral-7b-v2", rank=0.25)

    reader = _mock_reader(tuple())
    # AggregationService retorna sem ordem definida
    svc = _mock_aggregation_service((agg_low, agg_high, agg_mid))

    uc = _make_use_case(reader, svc, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    ranks = [a.rank_score.value for a in out.aggregates]
    assert ranks == sorted(ranks, reverse=True)
    assert ranks[0] == pytest.approx(0.75)
    assert ranks[-1] == pytest.approx(0.25)


def test_nan_rank_score_goes_to_end(tmp_path: Path) -> None:
    agg_nan = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.0)
    # Forçar NaN no rank_score via substituição direta
    import dataclasses

    agg_nan = dataclasses.replace(
        agg_nan,
        rank_score=RankScore(float("nan")),
    )
    agg_valid = _make_mock_agg("ID_230K", "mistral-7b", rank=0.40)

    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((agg_nan, agg_valid))

    uc = _make_use_case(reader, svc, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    assert not math.isnan(out.aggregates[0].rank_score.value)
    assert math.isnan(out.aggregates[-1].rank_score.value)


# ---------------------------------------------------------------------------
# e) Persistência: arquivo JSON criado em tmp_path com campos corretos
# ---------------------------------------------------------------------------


def test_json_summary_created_with_correct_fields(tmp_path: Path) -> None:
    agg_a = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.75, n_excl=1)
    agg_b = _make_mock_agg("ID_230K", "mistral-7b", rank=0.25)

    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((agg_a, agg_b))

    uc = _make_use_case(reader, svc, tmp_path)
    uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    expected_path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_aggregates.json"
    assert expected_path.exists(), "arquivo JSON de sumário não foi criado"

    data = json.loads(expected_path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2

    first = data[0]
    assert "base" in first
    assert "llm" in first
    assert "rank_score" in first
    assert "n_observations" in first
    assert "n_excluded_nan" in first
    assert first["base"]["value"] == "IDx_400k"
    assert first["rank_score"]["value"] == pytest.approx(0.75)


def test_json_uses_dataclasses_asdict_structure(tmp_path: Path) -> None:
    """Verifica que base/llm/rank_score são dicts aninhados (dataclasses.asdict)."""
    agg = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.60)
    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((agg,))

    uc = _make_use_case(reader, svc, tmp_path)
    uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_aggregates.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data[0]

    # dataclasses.asdict produz dicts aninhados para sub-dataclasses
    assert isinstance(item["base"], dict) and "value" in item["base"]
    assert isinstance(item["llm"], dict) and "value" in item["llm"]
    assert isinstance(item["rank_score"], dict) and "value" in item["rank_score"]


# ---------------------------------------------------------------------------
# f) Filtro por run_id: resultados de outro run_id são ignorados
# ---------------------------------------------------------------------------


def test_filter_by_run_id_ignores_other_runs(tmp_path: Path) -> None:
    """Resultados de run-002 não entram na agregação quando run_id='run-001'."""
    store = InMemoryResultStore()
    writer_a = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id="run-001")
    writer_b = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id="run-002")

    for qid in ["q01", "q02", "q03"]:
        writer_a.append(
            make_evaluation_result(
                answer=make_generated_answer(
                    row_id=make_row_id(run_id="run-001", question_id=qid, base="IDx_400k", llm="llama3-8b"),
                    base="IDx_400k",
                    llm="llama3-8b",
                    question_id=qid,
                ),
                final_score=0.80,
            )
        )
        writer_b.append(
            make_evaluation_result(
                answer=make_generated_answer(
                    row_id=make_row_id(run_id="run-002", question_id=qid, base="ID_230K", llm="mistral-7b"),
                    base="ID_230K",
                    llm="mistral-7b",
                    question_id=qid,
                ),
                final_score=0.50,
            )
        )

    reader = InMemoryResultReader(store)

    # Usamos AggregationService real com RankScoreCalculator (sem mock)
    # mas interceptamos o que foi passado a aggregate_all via side_effect
    captured: list[object] = []
    real_svc = AggregationService(RankScoreCalculator({}))

    svc_mock = MagicMock(spec=AggregationService)

    def capture_and_return(results: object, *, threshold: float) -> tuple:
        captured.extend(results)  # type: ignore[arg-type]
        return real_svc.aggregate_all(results, threshold=threshold)  # type: ignore[arg-type]

    svc_mock.aggregate_all.side_effect = capture_and_return

    uc = _make_use_case(reader, svc_mock, tmp_path)
    out = uc.execute(AggregateResultsInput(run_id="run-001", round_id=_ROUND_ID))

    # Apenas os 3 resultados de run-001 devem ter sido processados
    assert len(captured) == 3
    for r in captured:
        assert r.answer.base.value == "IDx_400k"  # type: ignore[attr-defined]

    assert out.n_total_results == 3


# ---------------------------------------------------------------------------
# g) AggregationService é injetado (não instanciado internamente) — via mock
# ---------------------------------------------------------------------------


def test_aggregation_service_is_injected_not_instantiated(tmp_path: Path) -> None:
    """Verifica que o use case delega 100% ao AggregationService injetado."""
    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((_make_mock_agg("IDx_400k", "llama3-8b", rank=0.5),))

    uc = _make_use_case(reader, svc, tmp_path)
    uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    svc.aggregate_all.assert_called_once()
    call_kwargs = svc.aggregate_all.call_args
    assert call_kwargs is not None
    # threshold deve ser o padrão 0.70
    assert call_kwargs.kwargs.get("threshold") == pytest.approx(0.70)


# ---------------------------------------------------------------------------
# h) Golden: recomputa valores a partir de 12 EvaluationResult sintéticos
# ---------------------------------------------------------------------------


def _build_golden_results(run_id: str, round_id: str) -> tuple:
    """Monta os 12 resultados do cenário golden e retorna como tupla.

    Config A (IDx_400k/llama3-8b): score=0.80 exceto q03-s42 (NaN). Anotação q01-s42 flag=0.
    Config B (ID_230K/mistral-7b): todas score=0.50. Anotação q01-s42 flag=0.
    """
    from inteligenciomica_eval.domain.entities import EvaluationResult

    _nan = float("nan")

    rows: list[EvaluationResult] = []

    # Config A: IDx_400k / llama3-8b
    for seed in [42, 43]:
        for qid in ["q01", "q02", "q03"]:
            is_nan = seed == 42 and qid == "q03"
            annotation = 0 if (seed == 42 and qid == "q01") else None
            final_score = _nan if is_nan else 0.80
            row_id = make_row_id(
                run_id=run_id, base="IDx_400k", llm="llama3-8b",
                seed=seed, question_id=qid,
            )
            rows.append(
                make_evaluation_result(
                    answer=make_generated_answer(
                        row_id=row_id,
                        base="IDx_400k",
                        llm="llama3-8b",
                        seed=seed,
                        question_id=qid,
                    ),
                    final_score=final_score,
                    critical_failure_flag=annotation,
                )
            )

    # Config B: ID_230K / mistral-7b
    for seed in [42, 43]:
        for qid in ["q01", "q02", "q03"]:
            annotation = 0 if (seed == 42 and qid == "q01") else None
            row_id = make_row_id(
                run_id=run_id, base="ID_230K", llm="mistral-7b",
                seed=seed, question_id=qid,
            )
            rows.append(
                make_evaluation_result(
                    answer=make_generated_answer(
                        row_id=row_id,
                        base="ID_230K",
                        llm="mistral-7b",
                        seed=seed,
                        question_id=qid,
                    ),
                    final_score=0.50,
                    critical_failure_flag=annotation,
                )
            )

    return tuple(rows)


def test_golden_aggregate_values(tmp_path: Path) -> None:
    """Verifica que os agregados reais batem com os valores do arquivo golden."""
    golden_path = (
        Path(__file__).parent.parent.parent / "golden" / "aggregate_results_expected.json"
    )
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    run_id = golden["inputs"]["run_id"]
    round_id = golden["inputs"]["round_id"]
    threshold = golden["inputs"]["failure_threshold"]

    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=round_id, run_id=run_id)
    for r in _build_golden_results(run_id, round_id):
        writer.append(r)

    reader = InMemoryResultReader(store)
    real_svc = AggregationService(RankScoreCalculator({}))

    uc = AggregateResultsUseCase(
        reader=reader,
        aggregation_service=real_svc,
        data_dir=tmp_path,
    )
    out = uc.execute(
        AggregateResultsInput(
            run_id=run_id,
            round_id=round_id,
            phase=golden["inputs"]["phase"],
            failure_threshold=threshold,
        )
    )

    assert out.n_total_results == golden["expected_n_total_results"]
    assert out.n_nan_excluded == golden["expected_n_nan_excluded"]
    assert out.n_configs == golden["expected_n_configs"]
    assert out.best_config.base.value == golden["expected_best_config_base"]
    assert out.best_config.llm.value == golden["expected_best_config_llm"]

    expected = golden["expected_aggregates"]
    assert len(out.aggregates) == len(expected)

    for agg, exp in zip(out.aggregates, expected):
        assert agg.base.value == exp["base"]["value"], f"base mismatch: {agg.base.value}"
        assert agg.llm.value == exp["llm"]["value"], f"llm mismatch: {agg.llm.value}"
        assert agg.mean_score == pytest.approx(exp["mean_score"], abs=1e-9)
        assert agg.median_score == pytest.approx(exp["median_score"], abs=1e-9)
        assert agg.min_score == pytest.approx(exp["min_score"], abs=1e-9)
        assert agg.iqr == pytest.approx(exp["iqr"], abs=1e-9)
        assert agg.failure_rate == pytest.approx(exp["failure_rate"], abs=1e-9)
        assert agg.critical_failure_rate == pytest.approx(
            exp["critical_failure_rate"], abs=1e-9
        )
        assert agg.win_rate == pytest.approx(exp["win_rate"], abs=1e-9)
        assert agg.rank_score.value == pytest.approx(exp["rank_score"]["value"], abs=1e-9)
        assert agg.n_observations == exp["n_observations"]
        assert agg.n_excluded_nan == exp["n_excluded_nan"]


# ---------------------------------------------------------------------------
# i) Caso vazio: run_id sem resultados levanta ValueError — testado
# ---------------------------------------------------------------------------


def test_empty_results_raises_value_error(tmp_path: Path) -> None:
    """Quando aggregate_all retorna (), execute() levanta ValueError — não IndexError."""
    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service(())  # sem configs

    uc = _make_use_case(reader, svc, tmp_path)
    with pytest.raises(ValueError, match="No results found"):
        uc.execute(AggregateResultsInput(run_id="missing-run", round_id=_ROUND_ID))


# ---------------------------------------------------------------------------
# j) JSON RFC 8259: NaN serializado como null, não como token NaN
# ---------------------------------------------------------------------------


def test_json_nan_serialized_as_null(tmp_path: Path) -> None:
    """Campos NaN (iqr, critical_failure_rate, rank_score) aparecem como null no JSON."""
    import dataclasses as dc

    from inteligenciomica_eval.domain.value_objects import RankScore

    agg = _make_mock_agg("IDx_400k", "llama3-8b", rank=0.5)
    # Força NaN em três campos representativos
    agg_nan = dc.replace(
        agg,
        iqr=float("nan"),
        critical_failure_rate=float("nan"),
        rank_score=RankScore(float("nan")),
    )

    reader = _mock_reader(tuple())
    svc = _mock_aggregation_service((agg_nan,))

    uc = _make_use_case(reader, svc, tmp_path)
    uc.execute(AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID))

    path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_aggregates.json"
    raw = path.read_text(encoding="utf-8")

    # Token "NaN" não deve aparecer no arquivo
    assert "NaN" not in raw, "JSON contém token NaN inválido (RFC 8259)"

    data = json.loads(raw)  # deve parsear sem erro
    item = data[0]
    assert item["iqr"] is None
    assert item["critical_failure_rate"] is None
    assert item["rank_score"]["value"] is None
