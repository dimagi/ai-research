from __future__ import annotations

import atexit
import dataclasses
import logging
import random
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings

from langfuse._client.get_client import _create_client_from_instance
from langfuse._client.resource_manager import LangfuseResourceManager


if TYPE_CHECKING:
    from langchain.callbacks.base import BaseCallbackHandler
    from langfuse import Langfuse


logger = logging.getLogger("ocs.tracing.langfuse")



class ServiceReentryException(Exception):
    pass


class ServiceNotInitializedException(Exception):
    pass


@dataclasses.dataclass
class TraceContext:
    """Context object for active traces and spans.

    Holds state and outputs, yielded from trace/span context managers.
    This unified class is used for both trace-level and span-level contexts.
    """

    id: UUID
    name: str
    outputs: dict[str, Any] = dataclasses.field(default_factory=dict)

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        """Set outputs for this trace/span. Can be called multiple times to merge outputs."""
        self.outputs |= outputs or {}


class LangFuseTracer:
    """
    Notes on langfuse:

    The API is designed to be used with a single set of credentials whereas we need to provide
    different credentials per call. This is why we don't use the standard 'observe' decorator.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = None
        self.trace_record = None

    @property
    def ready(self) -> bool:
        return bool(self.trace_record)

    @contextmanager
    def trace(
        self,
        name: str,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[TraceContext]:
        """Context manager for Langfuse trace lifecycle.

        Acquires a Langfuse client from ClientManager, creates a trace,
        and ensures the client is flushed on exit.
        """
        # Check for reentry
        if self.trace_record:
            raise ServiceReentryException("Service does not support reentrant use.")

        trace_context = TraceContext(id=uuid.uuid4(), name=name)
        # Get client and create trace
        self.client = client_manager.get(self.config)
        try:
            with self.client.start_as_current_span(
                name=trace_context.name,
                input=inputs,
                metadata=metadata,
            ) as trace:
                self.trace_record = trace

                yield trace_context

                # Update trace with outputs if any
                if outputs := trace_context.outputs:
                    trace.update(output=outputs.copy())
        finally:
            if self.trace_record:
                self.client.flush()

            # Reset state
            self.client = None
            self.trace_record = None
            self.session = None

    @contextmanager
    def span(
        self,
        name: str,
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[TraceContext]:
        """Context manager for Langfuse span lifecycle.

        Creates a nested span under the current observation (last span or root trace).
        """
        span_context = TraceContext(id=uuid.uuid4(), name=name)
        if not self.ready:
            yield span_context
            return

        with self.client.start_as_current_span(
            name=span_context.name,
            input=inputs,
            metadata=metadata,
        ) as span:
            yield span_context
            if output := span_context.outputs:
                span.update(output=output.copy())


class ClientManager:
    """This class manages the langfuse clients to avoid creating a new client for every request.
    On requests for a client it will also remove any clients that have been inactive for a
    certain amount of time."""

    def __init__(self, stale_timeout=300, prune_interval=60, max_clients=20) -> None:
        self.key_timestamps: dict[str, float] = {}
        self.stale_timeout = stale_timeout
        self.max_clients = max_clients
        self.prune_interval = prune_interval
        self._start_prune_thread()

    def get(self, config: dict) -> Langfuse:
        from langfuse import Langfuse

        public_key = config.get("public_key")
        with LangfuseResourceManager._lock:
            active_instances = LangfuseResourceManager._instances
            if target_instance := active_instances.get(public_key, None):
                client = _create_client_from_instance(target_instance, public_key)
            else:
                logger.debug("Creating new Langfuse client with public_key '%s'", public_key)
                client = Langfuse(**config)
            self.key_timestamps[public_key] = time.time()
        return client

    def _start_prune_thread(self):
        self._prune_thread = threading.Thread(target=self._prune_worker, daemon=True)
        self._prune_thread.start()

    def _prune_worker(self):
        while True:
            time.sleep(self.prune_interval)
            self._prune_stale()

    def _prune_stale(self):
        if not self.key_timestamps:
            return

        logger.debug("Pruning clients...")
        for public_key in list(self.key_timestamps.keys()):
            timestamp = self.key_timestamps[public_key]
            if time.time() - timestamp > self.stale_timeout:
                logger.debug("Pruning old client with public_key '%s'", public_key)
                self._remove_client(public_key)

        if len(self.key_timestamps) > self.max_clients:
            # remove the oldest clients until we are below the max
            sorted_keys = sorted(self.key_timestamps.items(), key=lambda x: x[1])
            keys_to_remove = sorted_keys[: len(self.key_timestamps) - self.max_clients]
            logger.debug("Pruned %d clients above max limit", len(keys_to_remove))
            for public_key, _ in keys_to_remove:
                self._remove_client(public_key)

    def _remove_client(self, public_key):
        with LangfuseResourceManager._lock:
            active_instances = LangfuseResourceManager._instances
            if target_instance := active_instances.pop(public_key, None):
                target_instance.shutdown()
            self.key_timestamps.pop(public_key)

    def shutdown(self):
        if self.key_timestamps:
            logger.debug("Shutting down all langfuse clients (%s)", len(self.key_timestamps))
        with LangfuseResourceManager._lock:
            LangfuseResourceManager.reset()
            self.key_timestamps.clear()


client_manager = ClientManager()


@atexit.register
def _shutdown():
    """Shutdown the client manager when the program exits."""
    client_manager.shutdown()


def get_random_langfuse_account():
    account_config = random.choice(settings.LANGFUSE_ACCOUNTS)
    print("using account: ", account_config["public_key"])
    return LangFuseTracer(account_config)
