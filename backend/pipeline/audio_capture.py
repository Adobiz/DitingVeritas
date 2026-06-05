"""WASAPI Loopback 系统音频捕获"""
import logging
from collections.abc import Callable

import numpy as np
import sounddevice as sd

from config import config

logger = logging.getLogger("diting.audio")


def _find_loopback_device() -> int:
    """查找 WASAPI loopback 设备，找不到回退默认输入"""
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    wasapi_id = None
    for i, api in enumerate(hostapis):
        if "WASAPI" in api["name"]:
            wasapi_id = i
            break

    # WASAPI loopback 设备关键词（不同系统叫法不同）
    loopback_keys = ("loopback", "立体声混音", "stereo mix", "扬声器", "speakers",
                     "耳机", "headphones", "输出", "output", "播放")

    if wasapi_id is not None:
        for i, dev in enumerate(devices):
            if dev["hostapi"] != wasapi_id:
                continue
            if dev["max_input_channels"] == 0:
                continue
            name = dev["name"].lower()
            if any(k in name for k in loopback_keys):
                logger.info(f"Loopback 设备: [{i}] {dev['name']}")
                return i

    # 回退：WASAPI 下任意有输入通道的设备
    if wasapi_id is not None:
        for i, dev in enumerate(devices):
            if dev["hostapi"] == wasapi_id and dev["max_input_channels"] > 0:
                logger.info(f"WASAPI 输入设备: [{i}] {dev['name']}")
                return i

    fallback = sd.default.device[0] or 0
    logger.warning(f"未找到 loopback，回退设备 [{fallback}]")
    return fallback


class AudioCapture:
    def __init__(self):
        self._stream: sd.InputStream | None = None
        self._running = False
        self._device = config.audio.device_index or _find_loopback_device()

    @property
    def running(self) -> bool:
        return self._running

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

        def _callback(indata: np.ndarray, frames, time_info, status):
            if status:
                logger.debug(f"音频状态: {status}")
            mono = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
            rms = float(np.sqrt(np.mean(mono**2) + 1e-10))
            try:
                on_chunk(mono, rms)
            except Exception as e:
                logger.error(f"音频回调异常: {e}")

        try:
            self._stream = sd.InputStream(
                device=self._device,
                channels=config.audio.channels,
                samplerate=config.audio.sample_rate,
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
