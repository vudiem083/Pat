"""Signature-based classification of runtime evidence.

Every signature lists the exact substrings that trigger it, a plain-language
cause and safe actions. Confidence reflects how specific the signature is; BAT
never assigns confidence 1.0 because log evidence alone rarely proves a root
cause.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Signature:
    key: str
    code: str
    patterns: tuple[re.Pattern[str], ...]
    cause: str
    actions: tuple[str, ...]
    confidence: float
    severity: str = "ERROR"


SIGNATURES: tuple[Signature, ...] = (
    Signature(
        key="out_of_memory",
        code="BAT-RUNTIME-001",
        patterns=(
            re.compile(r"out of memory", re.IGNORECASE),
            re.compile(r"std::bad_alloc"),
            re.compile(r"MemoryError"),
        ),
        cause="The server process ran out of memory while loading or running the world.",
        actions=(
            "Reduce the world size or view-distance in server.properties.",
            "Check host memory limits and whether other BAT jobs are running concurrently.",
            "Re-run the test on a host with more available memory.",
        ),
        confidence=0.75,
    ),
    Signature(
        key="missing_shared_library",
        code="BAT-RUNTIME-003",
        patterns=(
            re.compile(r"error while loading shared libraries", re.IGNORECASE),
            re.compile(r"GLIBC_\d", re.IGNORECASE),
        ),
        cause="The server executable cannot load a required system library on this host.",
        actions=(
            "Install the missing system library for the operator-supplied server build.",
            "Match the server build to the host OS/architecture.",
        ),
        confidence=0.8,
    ),
    Signature(
        key="permission_denied",
        code="BAT-RUNTIME-006",
        patterns=(
            re.compile(r"permission denied", re.IGNORECASE),
            re.compile(r"EACCES"),
        ),
        cause="The server could not read or write a file/directory in its environment.",
        actions=(
            "Check ownership/permissions of the environment directory and the server executable.",
            "Ensure the BAT process user can write to runtime/environments/<env>/server.",
        ),
        confidence=0.7,
    ),
    Signature(
        key="port_in_use",
        code="BAT-RUNTIME-006",
        patterns=(
            re.compile(r"failed to bind|address already in use|port is already in use", re.IGNORECASE),
        ),
        cause="The configured server port is already used by another process.",
        actions=(
            "Stop the other server or let BAT pick a free UDP port on the next run.",
            "Avoid running two runtime jobs that share a fixed port.",
        ),
        confidence=0.7,
    ),
    Signature(
        key="script_error",
        code="BAT-SCRIPT-001",
        patterns=(
            re.compile(r"\[Scripting\]\[error\]", re.IGNORECASE),
            re.compile(r"JavaScript error", re.IGNORECASE),
            re.compile(r"Uncaught exception.*\.js", re.IGNORECASE),
        ),
        cause="A behavior pack script raised an error during execution.",
        actions=(
            "Inspect the generated script and the game's script API version for the target release.",
            "Confirm the world enables the required script module and experiments.",
            "Check the referenced module version in the pack manifest dependencies.",
        ),
        confidence=0.8,
    ),
    Signature(
        key="manifest_or_pack_error",
        code="BAT-PACK-001",
        patterns=(
            re.compile(r"failed to load pack", re.IGNORECASE),
            re.compile(r"invalid manifest", re.IGNORECASE),
            re.compile(r"manifest.*(invalid|missing|malformed)", re.IGNORECASE),
            re.compile(r"pack.*uuid", re.IGNORECASE),
        ),
        cause="Minecraft rejected one of the installed packs, most often because of a manifest or "
        "UUID problem.",
        actions=(
            "Run validate_project and read the manifest findings.",
            "Check for duplicate header UUIDs between behavior and resource packs.",
            "Confirm min_engine_version is not newer than the server version.",
        ),
        confidence=0.7,
    ),
    Signature(
        key="world_corrupt",
        code="BAT-WORLD-001",
        patterns=(
            re.compile(r"failed to load level", re.IGNORECASE),
            re.compile(r"level\.dat", re.IGNORECASE),
            re.compile(r"corrupt", re.IGNORECASE),
        ),
        cause="The world data could not be loaded, possibly because level.dat or the LevelDB store "
        "is damaged or incomplete.",
        actions=(
            "Run validate_world and inspect the reported world findings.",
            "Restore the pre-change snapshot from runtime/snapshots.",
            "Re-create the world skeleton and let Minecraft regenerate chunk data.",
        ),
        confidence=0.65,
    ),
    Signature(
        key="missing_file",
        code="BAT-RUNTIME-003",
        patterns=(
            re.compile(r"no such file or directory", re.IGNORECASE),
            re.compile(r"not found: bedrock_server", re.IGNORECASE),
        ),
        cause="A file required by the runtime (server binary, EULA, world or pack) is missing.",
        actions=(
            "Verify BAT_BEDROCK_SERVER points at an existing executable.",
            "Confirm the environment contains the expected world and packs.",
        ),
        confidence=0.6,
    ),
    Signature(
        key="eula",
        code="BAT-RUNTIME-006",
        patterns=(re.compile(r"eula|license agreement|you must agree", re.IGNORECASE),),
        cause="The server requires accepting its license/terms before it will start.",
        actions=(
            "Review and accept the applicable Minecraft server terms yourself; BAT will not "
            "accept licences on your behalf.",
        ),
        confidence=0.6,
    ),
    Signature(
        key="signal_segfault",
        code="BAT-RUNTIME-001",
        patterns=(re.compile(r"segmentation fault|SIGSEGV", re.IGNORECASE),),
        cause="The server process crashed at the native level (segmentation fault).",
        actions=(
            "Treat this as a server-build or host problem; check the exit code and OS logs.",
            "Retry on the same host to see whether the crash is reproducible before blaming your "
            "add-on.",
        ),
        confidence=0.6,
        severity="CRITICAL",
    ),
)

_METADATA_ONLY = Signature(
    key="no_signature_match",
    code="BAT-RUNTIME-001",
    patterns=(),
    cause="",
    actions=(),
    confidence=0.0,
)


@dataclass
class Classification:
    matches: list[Signature] = field(default_factory=list)
    scanned_chars: int = 0

    @property
    def matched(self) -> bool:
        return bool(self.matches)

    @property
    def confidence(self) -> float:
        if not self.matches:
            return 0.15
        strongest = max(self.matches, key=lambda s: s.confidence)
        # More independent signatures reinforce, but never reach certainty.
        boost = min(0.1, 0.03 * (len(self.matches) - 1))
        return round(min(0.9, strongest.confidence + boost), 2)

    @property
    def causes(self) -> list[str]:
        return [m.cause for m in self.matches]

    @property
    def actions(self) -> list[str]:
        seen: list[str] = []
        for match in self.matches:
            for action in match.actions:
                if action not in seen:
                    seen.append(action)
        return seen

    @property
    def codes(self) -> list[str]:
        return sorted({m.code for m in self.matches})

    @property
    def severity(self) -> str:
        order = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
        if not self.matches:
            return "ERROR"
        return max((m.severity for m in self.matches), key=lambda s: order.get(s, 2))


def classify_text(text: str) -> Classification:
    classification = Classification(scanned_chars=len(text))
    for signature in SIGNATURES:
        if any(pattern.search(text) for pattern in signature.patterns):
            classification.matches.append(signature)
    return classification


def classify_lines(lines: list[str]) -> Classification:
    return classify_text("\n".join(lines))
