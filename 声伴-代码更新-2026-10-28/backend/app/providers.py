"""第三方能力的可替换边界。

供应商未配置时，不发送用户乐谱，也绝不返回伪造的识谱/音频结果。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import settings


class ProviderNotConfigured(RuntimeError):
    pass


@dataclass
class RecognitionResult:
    musicxml: bytes
    midi: bytes


class OMRProvider(Protocol):
    def recognize(self, image_path: Path) -> RecognitionResult: ...


class AudioRenderer(Protocol):
    def render(self, midi_path: Path, kind: str, semitone: int, tempo_bpm: int) -> bytes: ...


class UnconfiguredOMR:
    def recognize(self, image_path: Path) -> RecognitionResult:
        raise ProviderNotConfigured("尚未配置 OMR_PROVIDER / OMR_API_KEY；上传乐谱不会被冒充为已识别。")


class UnconfiguredRenderer:
    def render(self, midi_path: Path, kind: str, semitone: int, tempo_bpm: int) -> bytes:
        raise ProviderNotConfigured("尚未配置 AUDIO_RENDERER / AUDIO_API_KEY；不会生成伪造伴奏。")


def omr_provider() -> OMRProvider:
    # 新服务商接入时，在此添加其适配器并保留相同的 recognize() 返回值契约。
    if settings.omr_provider == "unconfigured":
        return UnconfiguredOMR()
    raise ProviderNotConfigured(f"OMR 供应商“{settings.omr_provider}”尚未实现适配器。")


def audio_renderer() -> AudioRenderer:
    # 新渲染服务接入时，在此添加其适配器并保留相同的 render() 返回值契约。
    if settings.audio_renderer == "unconfigured":
        return UnconfiguredRenderer()
    raise ProviderNotConfigured(f"音频渲染服务“{settings.audio_renderer}”尚未实现适配器。")
