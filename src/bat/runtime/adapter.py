"""Runtime adapter abstraction.

BAT never bundles or redistributes Minecraft server binaries. The adapter turns
an operator-supplied executable into a process BAT can supervise. Because the
adapter is an interface, a Docker or client adapter can be added without
touching job, diagnostic or API code.

Honesty rules encoded here:
  * :class:`UnavailableAdapter` never pretends a server exists.
  * Adapters report what they can and cannot verify (server-side vs client-side).
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..config import Settings
from ..core.errors import make_error
from ..core.models import RuntimeType


@dataclass
class AdapterCapabilities:
    server_side: bool = True
    client_side: bool = False
    console_commands: bool = True
    script_errors: bool = True
    game_tests: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class ServerSpec:
    """Everything needed to launch one runtime server instance."""

    server_dir: Path
    world_dir: Path
    world_name: str = "Bedrock level"
    extra_args: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class RuntimeAdapter(Protocol):
    name: str
    runtime_type: RuntimeType
    capabilities: AdapterCapabilities

    def available(self) -> bool: ...

    def unavailable_reason(self) -> str: ...

    def build_command(self, spec: ServerSpec) -> list[str]: ...

    def describe(self) -> dict[str, object]: ...


class BDSAdapter:
    """Runs an operator-supplied Bedrock Dedicated Server executable."""

    name = "bds"
    runtime_type = RuntimeType.BDS
    capabilities = AdapterCapabilities(
        server_side=True,
        client_side=False,
        console_commands=True,
        script_errors=True,
        game_tests=False,
        notes=[
            "Bedrock Dedicated Server only exercises server-side behaviour.",
            "Rendering, textures, UI, attachables and mobile import flows need a client.",
        ],
    )

    def __init__(self, executable: Path | None) -> None:
        self.executable = Path(executable) if executable else None

    def available(self) -> bool:
        if self.executable is None:
            return False
        if not self.executable.is_file():
            return False
        if os.name != "nt" and not os.access(self.executable, os.X_OK):
            return False
        return True

    def unavailable_reason(self) -> str:
        if self.executable is None:
            return (
                "No Bedrock Dedicated Server executable is configured. Set BAT_BEDROCK_SERVER to "
                "your own bedrock_server path and ensure you comply with Mojang's terms. BAT "
                "does not download or redistribute server binaries."
            )
        if not self.executable.is_file():
            return f"Configured server executable does not exist: {self.executable}"
        if os.name != "nt" and not os.access(self.executable, os.X_OK):
            return f"Configured server executable is not executable: {self.executable}"
        return "Server executable is available."

    def build_command(self, spec: ServerSpec) -> list[str]:
        if not self.available():
            raise make_error("BAT-RUNTIME-003", self.unavailable_reason())
        command = [str(self.executable)]
        command.extend(spec.extra_args)
        return command

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "runtime_type": self.runtime_type.value,
            "available": self.available(),
            "executable": str(self.executable) if self.executable else None,
            "reason": self.unavailable_reason(),
            "platform": platform.system(),
            "capabilities": self.capabilities.__dict__,
        }


class UnavailableAdapter:
    """Adapter used when no runtime can be launched.

    It refuses to start anything instead of faking a session, so tests are
    reported as NOT_TESTED rather than PASS.
    """

    name = "unavailable"
    runtime_type = RuntimeType.UNAVAILABLE
    capabilities = AdapterCapabilities(
        server_side=False,
        client_side=False,
        console_commands=False,
        script_errors=False,
        game_tests=False,
        notes=["No Minecraft runtime is configured for this BAT installation."],
    )

    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or (
            "No runtime adapter is configured. Set BAT_RUNTIME_ADAPTER=bds and "
            "BAT_BEDROCK_SERVER=/path/to/bedrock_server to run real server tests."
        )

    def available(self) -> bool:
        return False

    def unavailable_reason(self) -> str:
        return self.reason

    def build_command(self, spec: ServerSpec) -> list[str]:
        raise make_error("BAT-RUNTIME-003", self.reason)

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "runtime_type": self.runtime_type.value,
            "available": False,
            "executable": None,
            "reason": self.reason,
            "platform": platform.system(),
            "capabilities": self.capabilities.__dict__,
        }


def select_adapter(settings: Settings) -> RuntimeAdapter:
    mode = settings.runtime_adapter
    executable = settings.bedrock_server_path
    if mode == "none":
        return UnavailableAdapter("Runtime testing is disabled (BAT_RUNTIME_ADAPTER=none).")
    if mode in {"bds", "auto"}:
        candidate = BDSAdapter(executable or _discover_server(settings))
        if candidate.available():
            return candidate
        # A misconfigured path must not take the whole toolkit down: report it
        # honestly as unavailable and let runtime calls fail with BAT-RUNTIME-003.
        return UnavailableAdapter(candidate.unavailable_reason())
    raise make_error(
        "BAT-INPUT-001",
        f"Unknown BAT_RUNTIME_ADAPTER {mode!r}. Use bds, auto or none.",
    )


def _discover_server(settings: Settings) -> Path | None:
    """Look for an operator-provided server next to the runtime root."""
    for name in ("bedrock_server", "bedrock_server.exe"):
        candidate = settings.runtime_root / "server" / name
        if candidate.is_file():
            return candidate
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def adapter_summary(adapter: RuntimeAdapter) -> dict[str, object]:
    return adapter.describe()
