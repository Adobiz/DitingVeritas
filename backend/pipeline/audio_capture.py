"""WASAPI Loopback 系统音频捕获"""
import logging
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from config import config

_TARGET_SR = 16000  # VAD/ASR 统一使用 16kHz


def _resample(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    """降采样到 16kHz（线性插值）"""
    if orig_sr == _TARGET_SR:
        return audio
    dur = len(audio) / orig_sr
    n = max(1, int(dur * _TARGET_SR))
    return np.interp(
        np.linspace(0, dur, n),
        np.linspace(0, dur, len(audio)),
        audio,
    ).astype(np.float32)

logger = logging.getLogger("diting.audio")


def _find_loopback_device() -> int:
    devices = sd.query_devices()
    keys = ("立体声混音", "stereo mix", "wave out mix", "loopback", "what u hear")

    for i, dev in enumerate(devices):
        if dev["max_input_channels"] == 0:
            continue
        if any(k in dev["name"].lower() for k in keys):
            logger.info(f"Loopback: [{i}] {dev['name']}")
            return i

    logger.warning("未找到 loopback 设备！请在 Windows 声音设置中启用立体声混音。")
    return sd.default.device[0] or 0



class AudioCapture:
    def __init__(self):
        self._stream: sd.InputStream | None = None
        self._running = False
        self._error: str | None = None
        self._device = config.audio.device_index or _find_loopback_device()
        self._sample_rate = config.audio.sample_rate or \
            int(sd.query_devices(self._device)["default_samplerate"])

    @property
    def running(self) -> bool:
        return self._running

    @property
    def error(self) -> str | None:
        return self._error

    def list_devices(self) -> list[dict]:
        return [
            {
                "id": i,
                "name": d["name"],
                "channels_in": d["max_input_channels"],
                "sample_rate": d["default_samplerate"],
            }
            for i, d in enumerate(sd.query_devices())
        ]

    def start(self, on_chunk: Callable[[np.ndarray, float], None]):
        if self._running:
            return

        self._error = None
        errors = 0
        max_errors = 10  # 连续 10 次异常则熔断

        def _callback(indata: np.ndarray, frames, time_info, status):
            nonlocal errors
            if status:
                logger.debug(f"音频状态: {status}")
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            # 重采样到 16kHz
            mono = _resample(mono, self._sample_rate)
            rms = float(np.sqrt(np.mean(mono**2) + 1e-10))
            try:
                on_chunk(mono, rms)
                errors = 0
            except Exception as e:
                errors += 1
                logger.error(f"音频回调异常 ({errors}/{max_errors}): {e}")
                if errors >= max_errors:
                    self._error = f"回调连续异常 {errors} 次，已熔断"
                    logger.critical(self._error)
                    raise sd.CallbackAbort()

        try:
            self._stream = sd.InputStream(
                device=self._device,
                channels=config.audio.channels,
                samplerate=self._sample_rate,
                blocksize=config.audio.block_size,
                dtype="float32",
                callback=_callback,
            )
            self._stream.start()
            self._running = True
            logger.info(f"音频捕获已启动 (device={self._device})")
        except sd.PortAudioError as e:
            raise OSError(f"音频设备不可用: {e}") from e

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("音频捕获已停止")
