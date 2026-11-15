"""Version constants shared by every BAT module."""

__version__ = "0.1.0"

#: Lowest Minecraft Bedrock version BAT claims awareness of.
SUPPORTED_VERSION_MIN = "1.19.0"

#: Highest Minecraft Bedrock version BAT claims awareness of.
SUPPORTED_VERSION_MAX = "1.21.80"

#: The version used when a caller does not specify one.
DEFAULT_TARGET_VERSION = SUPPORTED_VERSION_MAX
