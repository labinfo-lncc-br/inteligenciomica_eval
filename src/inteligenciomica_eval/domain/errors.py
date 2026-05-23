from __future__ import annotations


class InteligenciomicaEvalError(Exception):
    """Base para todas as exceções do pacote inteligenciomica-eval.

    Capturar esta classe é suficiente para tratar qualquer erro do domínio.
    """


# ---------------------------------------------------------------------------
# Domínio / validação
# ---------------------------------------------------------------------------


class InvalidBaseIdError(InteligenciomicaEvalError):
    """Identificador de base de conhecimento inválido ou não reconhecido.

    Args:
        base_id: valor fornecido que falhou na validação.
    """

    def __init__(self, base_id: str) -> None:
        super().__init__(
            f"Invalid knowledge-base ID: {base_id!r}. Check allowed values."
        )
        self.base_id = base_id


class InvalidLLMIdError(InteligenciomicaEvalError):
    """Identificador de modelo LLM inválido ou malformado.

    Args:
        llm_id: valor fornecido que falhou na validação.
    """

    def __init__(self, llm_id: str) -> None:
        super().__init__(
            f"Invalid LLM ID: {llm_id!r}. Verify the model identifier format."
        )
        self.llm_id = llm_id


class ScoreOutOfRangeError(InteligenciomicaEvalError):
    """Score numérico fora do intervalo permitido [min, max].

    Args:
        score: valor recebido.
        min_val: limite inferior inclusivo.
        max_val: limite superior inclusivo.
    """

    def __init__(self, score: float, min_val: float, max_val: float) -> None:
        super().__init__(
            f"Score {score} is outside the allowed range [{min_val}, {max_val}]."
        )
        self.score = score
        self.min_val = min_val
        self.max_val = max_val


class WeightsDoNotSumToOneError(InteligenciomicaEvalError):
    """Pesos de métricas não somam 1.0 dentro da tolerância esperada.

    Args:
        actual_sum: soma calculada dos pesos fornecidos.
        tolerance: tolerância de arredondamento usada na validação.
    """

    def __init__(self, actual_sum: float, tolerance: float = 1e-6) -> None:
        super().__init__(
            f"Metric weights sum to {actual_sum:.6f}, expected 1.0 "
            f"(tolerance={tolerance}). Adjust weights so they total 1.0."
        )
        self.actual_sum = actual_sum
        self.tolerance = tolerance


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------


class ConfigValidationError(InteligenciomicaEvalError):
    """Configuração fornecida falhou na validação de esquema ou regras.

    Args:
        field: campo ou chave de configuração que causou o erro.
        reason: descrição do motivo da falha.
    """

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"Configuration error in field {field!r}: {reason}")
        self.field = field
        self.reason = reason


class ModelNotInRegistryError(InteligenciomicaEvalError):
    """Modelo solicitado não está registrado no catálogo de modelos disponíveis.

    Args:
        model_id: identificador do modelo ausente.
    """

    def __init__(self, model_id: str) -> None:
        super().__init__(
            f"Model {model_id!r} is not in the registry. "
            "Ensure the model is registered before use."
        )
        self.model_id = model_id


# ---------------------------------------------------------------------------
# Adapters / I/O
# ---------------------------------------------------------------------------


class RetrievalError(InteligenciomicaEvalError):
    """Falha ao recuperar documentos ou chunks da base de conhecimento.

    Args:
        reason: descrição técnica do problema de recuperação.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Retrieval failed: {reason}")
        self.reason = reason


class GenerationError(InteligenciomicaEvalError):
    """Falha durante a geração de texto pelo modelo de linguagem.

    Args:
        reason: descrição técnica do problema de geração.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Generation failed: {reason}")
        self.reason = reason


class JudgeUnavailableError(InteligenciomicaEvalError):
    """Modelo juiz inacessível ou sem resposta no tempo limite.

    Args:
        judge_id: identificador do modelo juiz.
        reason: descrição do motivo da indisponibilidade.
    """

    def __init__(self, judge_id: str, reason: str) -> None:
        super().__init__(f"Judge model {judge_id!r} is unavailable: {reason}")
        self.judge_id = judge_id
        self.reason = reason


class LLMOutputParseError(InteligenciomicaEvalError):
    """Saída do LLM não pôde ser interpretada no formato esperado.

    Args:
        expected_format: descrição do formato esperado.
        reason: motivo pelo qual o parsing falhou.
    """

    def __init__(self, expected_format: str, reason: str) -> None:
        super().__init__(f"Failed to parse LLM output as {expected_format!r}: {reason}")
        self.expected_format = expected_format
        self.reason = reason


class MetricComputationError(InteligenciomicaEvalError):
    """Erro durante o cálculo de uma métrica de avaliação.

    Args:
        metric_name: nome da métrica que falhou.
        reason: descrição do problema.
    """

    def __init__(self, metric_name: str, reason: str) -> None:
        super().__init__(f"Metric {metric_name!r} computation failed: {reason}")
        self.metric_name = metric_name
        self.reason = reason


class StorageError(InteligenciomicaEvalError):
    """Falha ao ler ou gravar dados no sistema de armazenamento.

    Args:
        operation: operação que falhou (ex: 'read', 'write', 'delete').
        reason: descrição técnica do problema.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(f"Storage {operation!r} operation failed: {reason}")
        self.operation = operation
        self.reason = reason


# ---------------------------------------------------------------------------
# Orquestração de servidores
# ---------------------------------------------------------------------------


class ServerStartTimeoutError(InteligenciomicaEvalError):
    """Servidor de modelo não iniciou dentro do prazo máximo de espera.

    Args:
        server_name: identificação do servidor (ex: nome ou endereço).
        timeout_seconds: limite de tempo aguardado em segundos.
    """

    def __init__(self, server_name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"Server {server_name!r} did not start within {timeout_seconds}s. "
            "Check server logs and resource availability."
        )
        self.server_name = server_name
        self.timeout_seconds = timeout_seconds


class ModelSwitchError(InteligenciomicaEvalError):
    """Falha ao trocar o modelo ativo em um servidor em execução.

    Args:
        from_model: modelo que estava ativo.
        to_model: modelo para o qual a troca foi tentada.
        reason: descrição do motivo da falha.
    """

    def __init__(self, from_model: str, to_model: str, reason: str) -> None:
        super().__init__(
            f"Failed to switch model from {from_model!r} to {to_model!r}: {reason}"
        )
        self.from_model = from_model
        self.to_model = to_model
        self.reason = reason


# ---------------------------------------------------------------------------
# Estatística
# ---------------------------------------------------------------------------


class InsufficientSampleError(InteligenciomicaEvalError):
    """Amostra insuficiente para calcular a estatística com confiança mínima exigida.

    Args:
        actual_size: tamanho da amostra disponível.
        required_size: tamanho mínimo necessário para o cálculo.
    """

    def __init__(self, actual_size: int, required_size: int) -> None:
        super().__init__(
            f"Sample size {actual_size} is below the required minimum of {required_size}. "
            "Collect more data before computing statistics."
        )
        self.actual_size = actual_size
        self.required_size = required_size
