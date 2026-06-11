# 常见问题

## 安装与启动

### Q: 双击 EXE 没反应？

A: 检查 `win-unpacked` 文件夹是否完整，双击里面的 `DitingVeritas.exe`。下载最新0.7.0版本。

### Q: 提示缺少 ffmpeg.dll？

A: 确保 `ffmpeg.dll` 在 EXE 同目录下。重新构建 `build.bat` 会自动带上。

### Q: 提示 `ModuleNotFoundError: No module named 'xxx'`？

A: 这是开发版用 `npm run electron:dev` 的报错。`pip install -r requirements.txt` 安装依赖。发行版打包好的 EXE 不会有这个问题。

---

## 音频

### Q: 所有音频设备均无法打开 / 切换音频源后报错？

A: 进入 Windows 设置 → 声音 → 输入 → 启用「立体声混音」设备。如果已启用，尝试禁用再重新启用。

### Q: 能启动但识别不到声音？

A: 检查「立体声混音」是否静音（音量调到 100%），确认正在播放音频。如果仍不行，尝试在设备下拉框里切换其他设备。

### Q: 立体声混音不工作？

A: 不同电脑的音频设备不同。在设备下拉框里逐个尝试，系统声音在哪个音频源播放，就找那个。WASAPI loopback 是自动探测的，不需要手动启用立体声混音。

---

## 翻译

### Q: 强化模式云端翻译不显示，必须暂停才出现？

A: 这是网络延迟导致的。切换到「均衡」或「稳定」模式，后端会自动给云端 API 加防抖和更短的切句间隔。或者改用本地模型（零延迟）。

### Q: 翻译出现 `<unk>` 或重复字符（谢谢谢谢）？

A: 本地 NLLB 模型在某些输入上会退化。已通过 `repetition_penalty` 和 `replace_unknowns` 缓解。如果频繁出现，建议切换到云端 API。

### Q: 本地模型翻译延迟大？

A: CPU 推理 ~1-2s 正常。勾选 GPU 加速（需 NVIDIA 显卡）可将延迟降到 ~0.3s。

### Q: GPU 加速开关灰色不能用？

A: 只支持 NVIDIA CUDA。AMD 显卡、核显不支持，这是 faster-whisper 底层的限制，不是 bug。

### Q: 云端 API 换模型不生效？

A: 停止翻译 → 切换模型 → 重新开始。后端每次启动都会热刷新配置。

### Q: 本地模型 不生效？

A: NLLB 经过验证，稳定可工作。 CTranslate2 转换翻译模型基本都可以运行，其他的模型未经测试，可能有兼容性问题，不推荐使用，后续会慢慢优化。

---

## 设置与存储

### Q: 添加的模型重启后会不会消失？

A: `userData` 固定到 `%APPDATA%/DitingVeritas`，重启不会丢失。

### Q: 闻境（URL 语境）不生效？

A: 闻境只对云端 LLM（Claude/DeepSeek/OpenAI）生效。本地大部分翻译模型没有 system prompt，无法注入语境。

### Q: 切换音频源后前端显示还是旧的？

A: 每次点开音频源下拉框都会实时刷新设备列表，选择后点击▶重新开始即生效。

---

## 构建与分发

### Q: `build.bat` 运行报错 `pyinstaller: command not found`？

A: `pip install pyinstaller`。`build.bat` 是给开发者用的，普通用户不需要。

### Q: 打包后的文件太大（>2GB）？

A: 因为 torch（~2GB）被打包进了后端 EXE。暂时无法显著缩小。分发时使用 7z 分卷压缩。
