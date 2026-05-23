from __future__ import annotations

import pytest

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    GenerationError,
    InsufficientSampleError,
    InteligenciomicaEvalError,
    InvalidBaseIdError,
    InvalidLLMIdError,
    JudgeUnavailableError,
    LLMOutputParseError,
    MetricComputationError,
    ModelNotInRegistryError,
    ModelSwitchError,
    RetrievalError,
    ScoreOutOfRangeError,
    ServerStartTimeoutError,
    StorageError,
    WeightsDoNotSumToOneError,
)

# ---------------------------------------------------------------------------
# Hierarquia: todas as subclasses descendem de InteligenciomicaEvalError
# ---------------------------------------------------------------------------

ALL_SUBCLASSES: list[type[InteligenciomicaEvalError]] = [
    # Domínio / validação
    InvalidBaseIdError,
    InvalidLLMIdError,
    ScoreOutOfRangeError,
    WeightsDoNotSumToOneError,
    # Configuração
    ConfigValidationError,
    ModelNotInRegistryError,
    # Adapters / I/O
    RetrievalError,
    GenerationError,
    JudgeUnavailableError,
    LLMOutputParseError,
    MetricComputationError,
    StorageError,
    # Orquestração de servidores
    ServerStartTimeoutError,
    ModelSwitchError,
    # Estatística
    InsufficientSampleError,
]


@pytest.mark.parametrize("exc_class", ALL_SUBCLASSES, ids=lambda c: c.__name__)
@pytest.mark.unit
def test_each_subclass_is_subclass_of_base(
    exc_class: type[InteligenciomicaEvalError],
) -> None:
    assert issubclass(exc_class, InteligenciomicaEvalError)


@pytest.mark.unit
def test_base_is_subclass_of_exception() -> None:
    assert issubclass(InteligenciomicaEvalError, Exception)


# ---------------------------------------------------------------------------
# Captura pela base: um representante de cada grupo
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_base_catches_domain_validation_group() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        raise InvalidBaseIdError("unknown-base")


@pytest.mark.unit
def test_base_catches_config_group() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        raise ConfigValidationError("llm_id", "field is required")


@pytest.mark.unit
def test_base_catches_adapters_io_group() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        raise RetrievalError("vector store timed out")


@pytest.mark.unit
def test_base_catches_server_orchestration_group() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        raise ServerStartTimeoutError("ollama", 30.0)


@pytest.mark.unit
def test_base_catches_statistics_group() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        raise InsufficientSampleError(actual_size=3, required_size=30)


# ---------------------------------------------------------------------------
# Constructors: atributos contextuais preservados
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_invalid_base_id_stores_attribute() -> None:
    err = InvalidBaseIdError("bad-id")
    assert err.base_id == "bad-id"
    assert "bad-id" in str(err)


@pytest.mark.unit
def test_invalid_llm_id_stores_attribute() -> None:
    err = InvalidLLMIdError("gpt-X")
    assert err.llm_id == "gpt-X"


@pytest.mark.unit
def test_score_out_of_range_stores_bounds() -> None:
    err = ScoreOutOfRangeError(1.5, 0.0, 1.0)
    assert err.score == 1.5
    assert err.min_val == 0.0
    assert err.max_val == 1.0
    assert "1.5" in str(err)


@pytest.mark.unit
def test_weights_do_not_sum_to_one_stores_actual_sum() -> None:
    err = WeightsDoNotSumToOneError(actual_sum=0.9)
    assert err.actual_sum == pytest.approx(0.9)
    assert "0.9" in str(err)


@pytest.mark.unit
def test_config_validation_error_stores_field_and_reason() -> None:
    err = ConfigValidationError("timeout", "must be positive")
    assert err.field == "timeout"
    assert err.reason == "must be positive"


@pytest.mark.unit
def test_model_not_in_registry_stores_model_id() -> None:
    err = ModelNotInRegistryError("llama-99")
    assert err.model_id == "llama-99"


@pytest.mark.unit
def test_retrieval_error_stores_reason() -> None:
    err = RetrievalError("connection refused")
    assert err.reason == "connection refused"


@pytest.mark.unit
def test_generation_error_stores_reason() -> None:
    err = GenerationError("token limit exceeded")
    assert err.reason == "token limit exceeded"


@pytest.mark.unit
def test_judge_unavailable_stores_judge_id_and_reason() -> None:
    err = JudgeUnavailableError("gpt-4o", "rate limit")
    assert err.judge_id == "gpt-4o"
    assert err.reason == "rate limit"


@pytest.mark.unit
def test_llm_output_parse_error_stores_format_and_reason() -> None:
    err = LLMOutputParseError("JSON", "unexpected EOF")
    assert err.expected_format == "JSON"
    assert err.reason == "unexpected EOF"


@pytest.mark.unit
def test_metric_computation_error_stores_metric_and_reason() -> None:
    err = MetricComputationError("faithfulness", "division by zero")
    assert err.metric_name == "faithfulness"
    assert err.reason == "division by zero"


@pytest.mark.unit
def test_storage_error_stores_operation_and_reason() -> None:
    err = StorageError("write", "disk full")
    assert err.operation == "write"
    assert err.reason == "disk full"


@pytest.mark.unit
def test_server_start_timeout_stores_name_and_timeout() -> None:
    err = ServerStartTimeoutError("ollama", 60.0)
    assert err.server_name == "ollama"
    assert err.timeout_seconds == pytest.approx(60.0)


@pytest.mark.unit
def test_model_switch_error_stores_models_and_reason() -> None:
    err = ModelSwitchError("llama3", "mistral", "OOM")
    assert err.from_model == "llama3"
    assert err.to_model == "mistral"
    assert err.reason == "OOM"


@pytest.mark.unit
def test_insufficient_sample_stores_sizes() -> None:
    err = InsufficientSampleError(actual_size=5, required_size=50)
    assert err.actual_size == 5
    assert err.required_size == 50


# ---------------------------------------------------------------------------
# Tipagem: isinstance via base em blocos except reais
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_except_base_catches_all_subclasses() -> None:
    caught: list[str] = []
    for exc in [
        InvalidBaseIdError("x"),
        InvalidLLMIdError("y"),
        ScoreOutOfRangeError(2.0, 0.0, 1.0),
        WeightsDoNotSumToOneError(0.5),
        ConfigValidationError("f", "r"),
        ModelNotInRegistryError("m"),
        RetrievalError("r"),
        GenerationError("r"),
        JudgeUnavailableError("j", "r"),
        LLMOutputParseError("fmt", "r"),
        MetricComputationError("m", "r"),
        StorageError("op", "r"),
        ServerStartTimeoutError("s", 1.0),
        ModelSwitchError("a", "b", "r"),
        InsufficientSampleError(1, 10),
    ]:
        try:
            raise exc
        except InteligenciomicaEvalError as e:
            caught.append(type(e).__name__)

    assert len(caught) == len(ALL_SUBCLASSES)
