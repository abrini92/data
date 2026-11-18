"""Read-only Data IA platform (API + future HTML). Never writes the production registry."""

from data_ia.platform.app import create_app
from data_ia.platform.settings import PlatformSettings

__all__ = ["PlatformSettings", "create_app"]
