from __future__ import annotations

from dataclasses import dataclass

from inteligenciomica_eval.domain.ports import ModelSpec, ServerHandle

_PID_START = 9000


@dataclass
class StartCall:
    """Record of a single FakeVLLMServerManager.start invocation.

    Args:
        model: model specification that was passed.
        handle: server handle that was returned.
    """

    model: ModelSpec
    handle: ServerHandle


@dataclass
class WaitHealthyCall:
    """Record of a single FakeVLLMServerManager.wait_healthy invocation.

    Args:
        handle: server handle that was passed.
        timeout_s: timeout in seconds that was passed.
    """

    handle: ServerHandle
    timeout_s: int


@dataclass
class StopCall:
    """Record of a single FakeVLLMServerManager.stop invocation.

    Args:
        handle: server handle that was passed.
    """

    handle: ServerHandle


class FakeVLLMServerManager:
    """In-memory VLLMServerManagerPort recording lifecycle calls without I/O.

    Assigns synthetic PIDs and localhost URLs to returned handles. Records all
    start, wait_healthy, and stop calls for assertion in tests. No process is
    actually created or terminated.

    Args:
        base_port: starting port for synthetic server URLs; incremented per start call.
    """

    def __init__(self, *, base_port: int = 8000) -> None:
        self._base_port = base_port
        self._next_pid = _PID_START
        self.start_calls: list[StartCall] = []
        self.wait_calls: list[WaitHealthyCall] = []
        self.stop_calls: list[StopCall] = []

    def start(self, model: ModelSpec) -> ServerHandle:
        """Record the start call and return a synthetic ServerHandle.

        Args:
            model: model specification to load.

        Returns:
            ServerHandle with a synthetic PID and localhost URL.
        """
        port = self._base_port + len(self.start_calls)
        handle = ServerHandle(
            process_id=self._next_pid,
            base_url=f"http://localhost:{port}",
            model_id=model.model_id,
        )
        self._next_pid += 1
        self.start_calls.append(StartCall(model=model, handle=handle))
        return handle

    def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Record the wait_healthy call without blocking.

        Args:
            handle: server handle to wait on.
            timeout_s: timeout in seconds (recorded but not enforced).
        """
        self.wait_calls.append(WaitHealthyCall(handle=handle, timeout_s=timeout_s))

    def stop(self, handle: ServerHandle) -> None:
        """Record the stop call without any process termination.

        Args:
            handle: server handle to stop.
        """
        self.stop_calls.append(StopCall(handle=handle))
