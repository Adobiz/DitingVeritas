"""WASAPI Loopback 系统音频捕获 — 最终防崩版"""
import logging
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from config import config

_TARGET_SR = 16000
logger = logging.getLogger("diting.audio")


def _resample(audio: np.ndarray, orig_sr: int) -> np.ndarray:
    if orig_sr == _TARGET_SR:
        return audio
    dur = len(audio) / orig_sr
    n = max(1, int(dur * _TARGET_SR))
    return np.interp(
        np.linspace(0, dur, n),
        np.linspace(0, dur, len(audio)),
        audio,
    ).astype(np.float32)


def _safe_default_input() -> int:
    try:
        return int(sd.default.device[0]) or 0
    except Exception:
        return 0


def _find_loopback_device() -> int:
    try:
        devices = sd.query_devices()
    except Exception as e:
        logger.error(f"枚举设备失败: {e}")
        return _safe_default_input()

    keys = ("立体声混音", "stereo mix", "wave out mix", "loopback", "what u hear")
    for i, dev in enumerate(devices):
        try:
            if dev.get("max_input_channels", 0) == 0:
                continue
            if any(k in dev.get("name", "").lower() for k in keys):
                logger.info(f"Loopback: [{i}] {dev['name']}")
                return i
        except Exception:
            continue

    logger.warning("未找到 loopback 设备！请在 Windows 声音设置中启用立体声混音。")
    return _safe_default_input()


class AudioCapture:
    def __init__(self):
        self._stream: sd.InputStream | None = None
        self._running = False
        self._error: str | None = None
        self._device = config.audio.device_index or _find_loopback_device()
        try:
            dev_info = sd.query_devices(self._device)
            self._sample_rate = int(dev_info.get("default_samplerate", 48000))
        except Exception:
            self._sample_rate = 48000

    @property
    def running(self) -> bool:
        return self._running

    @property
    def error(self) -> str | None:
        return self._error

    def list_devices(self) -> list[dict]:
        try:
            devices = sd.query_devices()
        except Exception as e:
            logger.error(f"枚举设备失败: {e}")
            return []
        return [
            {
                "id": i,
                "name": d.get("name", "Unknown"),
                "channels_in": d.get("max_input_channels"),
                "sample_rate": d.get("default_samplerate"),
            }
            for i, d in enumerate(devices)
        ]

    def start(self, on_chunk: Callable[[np.ndarray, float], None]):
        if self._running:
            return

        self._error = None
        errors = 0
        max_errors = 10

        def _callback(indata: np.ndarray, frames, time_info, status):
            nonlocal errors
            if status:
                logger.debug(f"音频状态: {status}")
            try:
                mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            except Exception as e:
                logger.error(f"音频格式异常: {e}")
                return
            mono = _resample(mono, self._sample_rate)
            rms = float(np.sqrt(np.mean(mono ** 2) + 1e-10))
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

        def _try_open(dev, sr):
            try:
                s = sd.InputStream(
                    device=dev, channels=1, samplerate=sr,
                    blocksize=config.audio.block_size, dtype="float32",
                    callback=_callback,
                )
                s.start()
                return s
            except Exception as e:
                logger.debug(f"设备[{dev}]@{sr}Hz 打开失败: {e}")
                return None

        fallback_dev = _safe_default_input()

        for try_dev, try_srs in [
            (self._device, [self._sample_rate]),
            (self._device, [48000, 44100, 16000]),
            (fallback_dev, [48000, 44100, 16000]),
        ]:
            for sr in try_srs:
                if sr <= 0:
                    continue
                s = _try_open(try_dev, sr)
                if s:
                    self._stream = s
                    self._device = try_dev
                    self._sample_rate = sr
                    break
            if self._stream:
                break

        if self._stream is None:
            raise OSError("所有音频设备均无法打开")

        self._running = True
        logger.info(f"音频捕获已启动 (device={self._device}, sr={self._sample_rate})")

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning(f"关闭音频流异常: {e}")
            self._stream = None
            logger.info("音频捕获已停止")
