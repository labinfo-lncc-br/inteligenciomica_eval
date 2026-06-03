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


class InvalidSeedError(InteligenciomicaEvalError):
    """Semente de reprodutibilidade inválida — deve ser inteiro não-negativo (>= 0).

    Args:
        seed: valor fornecido que falhou na validação.
    """

    def __init__(self, seed: int) -> None:
        super().__init__(
            f"Invalid seed value: {seed}. Seed must be a non-negative integer (>= 0)."
        )
        self.seed = seed


class InvalidPhaseError(InteligenciomicaEvalError):
    """Fase de experimento inválida — deve ser ``'A'`` ou ``'B'``.

    Args:
        phase: valor fornecido que falhou na validação.
    """

    def __init__(self, phase: str) -> None:
        super().__init__(f"Invalid experiment phase: {phase!r}. Expected 'A' or 'B'.")
        self.phase = phase


class RetrievalTupleLengthMismatchError(InteligenciomicaEvalError):
    """Tuplas de retrieval com comprimentos diferentes.

    As três tuplas (``retrieved_chunk_ids``, ``retrieved_chunks_text``,
    ``retrieval_scores``) devem ter o mesmo número de elementos.

    Args:
        chunk_ids_len: comprimento de ``retrieved_chunk_ids``.
        chunks_text_len: comprimento de ``retrieved_chunks_text``.
        scores_len: comprimento de ``retrieval_scores``.
    """

    def __init__(
        self, chunk_ids_len: int, chunks_text_len: int, scores_len: int
    ) -> None:
        super().__init__(
            f"Retrieval tuples must have equal length; got "
            f"chunk_ids={chunk_ids_len}, chunks_text={chunks_text_len}, "
            f"scores={scores_len}."
        )
        self.chunk_ids_len = chunk_ids_len
        self.chunks_text_len = chunks_text_len
        self.scores_len = scores_len


class InvalidCriticalFailureFlagError(InteligenciomicaEvalError):
    """Flag de falha crítica fora do domínio ``{0, 1}``.

    Args:
        flag: valor fornecido que falhou na validação.
    """

    def __init__(self, flag: int) -> None:
        super().__init__(f"Invalid critical_failure_flag: {flag!r}. Expected 0 or 1.")
        self.flag = flag


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

    O contexto de diagnóstico (``pid``, ``reason`` e o ``stderr_tail`` do processo) é
    carregado na própria exceção, não apenas logado — quem captura (orquestrador,
    TAREFA-307) tem acesso programático à causa-raiz sem reparsear logs.

    Args:
        server_name: identificação do servidor (ex: nome ou endereço).
        timeout_seconds: limite de tempo aguardado em segundos.
        pid: PID do processo que falhou (quando conhecido).
        reason: causa estruturada (ex.: ``"timeout"`` ou ``"process_exited"``).
        stderr_tail: últimas linhas de ``stderr`` do processo (diagnóstico).
    """

    def __init__(
        self,
        server_name: str,
        timeout_seconds: float,
        *,
        pid: int | None = None,
        reason: str | None = None,
        stderr_tail: str | None = None,
    ) -> None:
        message = f"Server {server_name!r} did not start within {timeout_seconds}s"
        if pid is not None:
            message += f" (pid={pid})"
        if reason:
            message += f"; reason={reason}"
        message += ". Check server logs and resource availability."
        if stderr_tail:
            message += f"\n--- stderr tail ---\n{stderr_tail}"
        super().__init__(message)
        self.server_name = server_name
        self.timeout_seconds = timeout_seconds
        self.pid = pid
        self.reason = reason
        self.stderr_tail = stderr_tail


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


class InsufficientAnnotationError(InteligenciomicaEvalError):
    """Levantada quando a amostra anotada é menor que o mínimo configurado (TAREFA-602).

    Impede o cálculo de Cohen's κ quando não há dados suficientes para uma
    estimativa confiável da concordância entre juiz LLM e anotador humano.

    Args:
        n_valid: número de linhas válidas (com anotação E score não-NaN).
        min_required: tamanho mínimo exigido pela configuração.
    """

    def __init__(self, n_valid: int, min_required: int) -> None:
        super().__init__(
            f"Insufficient annotations for Cohen's κ: {n_valid} valid samples "
            f"(minimum required: {min_required}). Annotate more rows before validating."
        )
        self.n_valid = n_valid
        self.min_required = min_required
