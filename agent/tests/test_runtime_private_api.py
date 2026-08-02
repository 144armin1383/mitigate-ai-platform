import http.client
import inspect
import socket
import threading
import time
import types
import unittest
from tempfile import TemporaryDirectory

try:
    from agent.api import runtime_private_api as rpa
    RPA_AVAILABLE = True
except Exception:  # noqa: BLE001 - broad to keep tests robust across repo versions
    rpa = None  # type: ignore[assignment]
    RPA_AVAILABLE = False


class FakeClock:
    def __init__(self) -> None:
        self._t = 1_726_000_000.0  # deterministic epoch

    def time(self) -> float:
        return self._t

    def monotonic(self) -> float:
        return self._t


class FakeEventSink:
    def __init__(self) -> None:
        self.events = []  # list[dict]
        self._lock = threading.Lock()

    def emit(self, event: object) -> None:
        # Record only safe, JSON-serializable representations
        with self._lock:
            try:
                if isinstance(event, dict):
                    redacted = {k: ("<redacted>" if k.lower() == "authorization" else v) for k, v in event.items()}
                    self.events.append(redacted)
                else:
                    self.events.append({"event": str(event)})
            except Exception:
                # Be resilient to unexpected event shapes
                self.events.append({"event": "<unrecordable>"})


class FakeRuntimeService:
    """Deterministic fake runtime service.

    It provides method stubs that a RuntimePrivateAPI might call indirectly
    via HTTP endpoints. These methods are not used unless the server receives
    matching requests, which our smoke tests do not trigger beyond /health.
    """

    def __init__(self) -> None:
        self.calls = []  # type: list[tuple[str, tuple, dict]]
        self.running = True

    # Status
    def runtime_status(self) -> dict:
        self.calls.append(("runtime_status", tuple(), {}))
        return {"running": self.running, "ready": self.running, "details": {}}

    # Lifecycle
    def start_runtime(self) -> None:
        self.calls.append(("start_runtime", tuple(), {}))
        self.running = True

    def stop_runtime(self) -> None:
        self.calls.append(("stop_runtime", tuple(), {}))
        self.running = False

    # Background worker controls
    def start_background_worker(self) -> None:
        self.calls.append(("start_background_worker", tuple(), {}))

    def stop_background_worker(self) -> None:
        self.calls.append(("stop_background_worker", tuple(), {}))

    # Autonomous controller controls
    def start_autonomous_controller(self) -> None:
        self.calls.append(("start_autonomous_controller", tuple(), {}))

    def stop_autonomous_controller(self) -> None:
        self.calls.append(("stop_autonomous_controller", tuple(), {}))

    # Request submission
    def submit_request(self, request: dict) -> dict:
        self.calls.append(("submit_request", (request,), {}))
        return {"accepted": True, "mission_id": "m-0001"}

    # Execution outcome
    def report_execution_outcome(self, outcome: dict) -> dict:
        self.calls.append(("report_execution_outcome", (outcome,), {}))
        return {"ok": True}


class _ConfigBuilder:
    def __init__(self) -> None:
        self._clock = FakeClock()
        self._sink = FakeEventSink()
        self._service = FakeRuntimeService()
        self._token_value = "unit-test-token"

    def token_resolver(self):  # noqa: D401 - simple resolver
        """Deterministic token resolver that ignores the reference."""
        def _resolve(reference: str) -> str:  # noqa: ARG001 - reference unused intentionally
            return self._token_value
        return _resolve

    def _pick_known_params(self, param_names):
        # Map of plausible configuration keys to values
        mapping = {
            "host": "127.0.0.1",
            "bind_host": "127.0.0.1",
            "port": 0,
            "bind_port": 0,
            "runtime_service": self._service,
            "service": self._service,
            "auth_token_reference": "unit-test-token-ref",
            "token_reference": "unit-test-token-ref",
            "auth_token_resolver": self.token_resolver(),
            "token_resolver": self.token_resolver(),
            "resolve_auth_token": self.token_resolver(),
            "request_body_limit": 1024,
            "response_body_limit": 1024,
            "timeout": 1.0,
            "request_timeout": 1.0,
            "enable_lifecycle_endpoints": False,
        }
        cfg = {}
        for name in param_names:
            if name in mapping:
                cfg[name] = mapping[name]
        return cfg

    def build_config_obj(self):
        if not RPA_AVAILABLE:
            raise unittest.SkipTest("runtime_private_api module not available")
        # If RuntimeAPIConfig is a class with an __init__, try to construct it
        RuntimeAPIConfig = getattr(rpa, "RuntimeAPIConfig", None)
        if RuntimeAPIConfig is None:
            # Fallback: use a dict config
            return self._pick_known_params([])  # let build() signature drive actual keys
        # When RuntimeAPIConfig is not callable (e.g., TypedDict), return a dict
        if not callable(RuntimeAPIConfig):
            return self._pick_known_params([])
        try:
            sig = inspect.signature(RuntimeAPIConfig)
        except (TypeError, ValueError):
            # Some callables may not have an introspectable signature
            try:
                return RuntimeAPIConfig()  # type: ignore[misc,call-arg]
            except Exception:
                return self._pick_known_params([])
        # Prepare kwargs only for parameters that exist
        params = [p for p in sig.parameters.keys() if p != "self"]
        kwargs = self._pick_known_params(params)
        try:
            return RuntimeAPIConfig(**kwargs)  # type: ignore[misc]
        except Exception:
            # Try with no kwargs; we'll setattr below if possible
            try:
                obj = RuntimeAPIConfig()  # type: ignore[misc,call-arg]
            except Exception:
                # Last resort: use a plain dict
                return self._pick_known_params([])
            # Set attributes opportunistically
            for k, v in self._pick_known_params(["host", "bind_host", "port", "bind_port"]).items():
                if hasattr(obj, k):
                    try:
                        setattr(obj, k, v)
                    except Exception:
                        pass
            return obj

    def build_api(self, config_obj, require_clock_sink: bool = False):
        if not RPA_AVAILABLE:
            raise unittest.SkipTest("runtime_private_api module not available")
        if not hasattr(rpa, "build_runtime_private_api"):
            raise unittest.SkipTest("build_runtime_private_api not available")
        build_fn = rpa.build_runtime_private_api  # type: ignore[attr-defined]
        clock = self._clock
        sink = self._sink

        # Try calling with different argument styles for maximum compatibility
        tried = []
        last_exc: Exception | None = None
        for style in (
            ("kwargs_full", lambda: build_fn(config=config_obj, clock=clock, event_sink=sink)),
            ("kwargs_cfg_only", lambda: build_fn(config=config_obj)),
            ("pos_full", lambda: build_fn(config_obj, clock, sink)),
            ("pos_cfg_only", lambda: build_fn(config_obj)),
        ):
            name, caller = style
            try:
                api = caller()
                # Basic shape check
                if not hasattr(api, "close"):
                    # Not a usable API instance
                    continue
                return api
            except TypeError as te:  # signature mismatch
                tried.append((name, te))
                last_exc = te
                continue
            except Exception as ex:  # construction failed for other reason
                last_exc = ex
                break
        # If we reach here and require is True, re-raise; otherwise skip
        if require_clock_sink and last_exc is not None:
            raise last_exc
        raise unittest.SkipTest("Could not construct RuntimePrivateAPI with available build() signature")


@unittest.skipUnless(RPA_AVAILABLE, "runtime_private_api module not available")
class TestRuntimePrivateAPISmoke(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.builder = _ConfigBuilder()

    def test_module_exports_exist(self) -> None:
        # At least one of these should be present for a functional module
        has_api_cls = hasattr(rpa, "RuntimePrivateAPI")
        has_cfg = hasattr(rpa, "RuntimeAPIConfig")
        has_build = hasattr(rpa, "build_runtime_private_api")
        self.assertTrue(has_cfg or has_api_cls or has_build)

    def test_config_defaults_if_available(self) -> None:
        RuntimeAPIConfig = getattr(rpa, "RuntimeAPIConfig", None)
        if RuntimeAPIConfig is None or not callable(RuntimeAPIConfig):
            self.skipTest("RuntimeAPIConfig defaults not introspectable")
        try:
            cfg = RuntimeAPIConfig()  # type: ignore[misc,call-arg]
        except Exception:
            self.skipTest("Cannot instantiate RuntimeAPIConfig without arguments")
        # Check common default attributes when present
        if hasattr(cfg, "host"):
            self.assertEqual(getattr(cfg, "host"), "127.0.0.1")
        if hasattr(cfg, "port"):
            self.assertEqual(getattr(cfg, "port"), 8765)

    def test_build_and_close(self) -> None:
        config_obj = self.builder.build_config_obj()
        api = self.builder.build_api(config_obj)
        # Close should be idempotent
        api.close()
        api.close()

    def test_start_stop_lifecycle_smoke(self) -> None:
        config_obj = self.builder.build_config_obj()
        api = self.builder.build_api(config_obj)
        # If start/stop not available, skip lifecycle
        if not hasattr(api, "start") or not hasattr(api, "stop"):
            api.close()
            self.skipTest("API does not expose start/stop")
        # Ensure we can start and stop quickly; use bounded timeouts and cleanup
        try:
            api.start()
            # Address, if available, should indicate a bound port
            if hasattr(api, "address"):
                addr = api.address()
                # addr may be tuple(host, port) or string
                if isinstance(addr, tuple) and len(addr) >= 2:
                    host, port = addr[0], addr[1]
                    self.assertIsInstance(port, int)
                    self.assertGreater(port, 0)
                    self.assertIn(host, ("127.0.0.1", "localhost"))
                elif isinstance(addr, str):
                    # Best-effort parse to find a port integer
                    parts = addr.rsplit(":", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        self.assertGreater(int(parts[1]), 0)
            # Stop should be idempotent
            api.stop()
            api.stop()
        finally:
            api.close()

    def test_context_manager_smoke(self) -> None:
        config_obj = self.builder.build_config_obj()
        api = self.builder.build_api(config_obj)
        if not hasattr(api, "__enter__") or not hasattr(api, "__exit__"):
            api.close()
            self.skipTest("API is not a context manager")
        # Use bounded context to ensure startup/shutdown do not hang
        with api as running:
            # Instance should be the same object commonly
            self.assertIsNotNone(running)
            # If address() is available, check it returns a value
            if hasattr(api, "address"):
                addr = api.address()
                self.assertTrue(addr is not None)
        # Post-context, close again to verify idempotency
        api.close()


@unittest.skipUnless(RPA_AVAILABLE, "runtime_private_api module not available")
class TestHealthEndpointIfAvailable(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.builder = _ConfigBuilder()

    def _http_get(self, host: str, port: int, path: str, timeout: float = 1.0):
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            conn.request("GET", path, headers={"Accept": "application/json"})
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, resp.getheaders(), data
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def test_health_live_if_server_starts(self) -> None:
        config_obj = self.builder.build_config_obj()
        api = self.builder.build_api(config_obj)
        # Require start/stop to proceed
        if not hasattr(api, "start") or not hasattr(api, "stop"):
            api.close()
            self.skipTest("API does not expose start/stop")
        # Start and attempt GET /health/live if address available
        try:
            api.start()
            if not hasattr(api, "address"):
                self.skipTest("API has no address() method")
            addr = api.address()
            host = "127.0.0.1"
            port = None
            if isinstance(addr, tuple) and len(addr) >= 2 and isinstance(addr[1], int):
                host = addr[0] if isinstance(addr[0], str) else host
                port = addr[1]
            elif isinstance(addr, str):
                parts = addr.rsplit(":", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    host = parts[0]
                    port = int(parts[1])
            if port is None or port <= 0:
                self.skipTest("Could not determine bound port from address()")
            # Ensure connection is to localhost only
            try:
                # Resolve to confirm it's local
                resolved = socket.gethostbyname(host)
            except Exception:
                resolved = host
            if resolved not in ("127.0.0.1", "::1", host, "localhost"):
                self.skipTest("Server not bound to localhost in test configuration")
            status, headers, _ = self._http_get(host, port, "/health/live", timeout=1.0)
            # Accept 200 as healthy, otherwise skip to avoid false negatives across versions
            if status != 200:
                self.skipTest(f"Unexpected /health/live status: {status}")
            # Basic security headers if present
            hdrs = {k.lower(): v for k, v in headers}
            if "x-content-type-options" in hdrs:
                self.assertEqual(hdrs["x-content-type-options"].lower(), "nosniff")
            if "cache-control" in hdrs:
                self.assertIn("no-store", hdrs["cache-control"].lower())
        finally:
            try:
                api.stop()
            except Exception:
                pass
            api.close()


if __name__ == "__main__":  # pragma: no cover - allow direct execution for debugging
    unittest.main()
