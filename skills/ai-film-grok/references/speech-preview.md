# Speech-to-Speech 互动对白预演侧车

`speech-preview` 是 RTX 5090 上的私有实验候选，不是 `tts_backend`，也不得把音频直接送入 final。

## 固定运行面

- Python 3.11 隔离环境：`speech-to-speech==0.2.11`。
- STT：Whisper `large-v3`；LLM：llama.cpp + `Qwen3-4B-Instruct-2507` Q4_K_M；TTS：Qwen3-TTS CustomVoice。
- 服务仅绑定 `127.0.0.1:8765`，不启用 `--enable_llm_proxy`；Mac 端只可经 SSH tunnel 访问。
- 日文女性试听优先 `Ono_Anna`。日文男性质量未人工通过前，角色成片仍用既有 Edge 声线锁。

## 安装与启动门

安装模型或启动服务前，操作者必须实测：远端身份、HF 授权及 gated-file 请求、磁盘、Python 3.11/CUDA、队列空闲、可用 VRAM 至少 24 GiB、可用 RAM 至少 12 GiB。

运行 `aifilm speech-preview probe` 只校验本机 JSON argv 配置；它不下载、不连接也不启动。`start --confirm` 会先执行受控容量检查器，并且只接受明确带有 `--ws_host 127.0.0.1`、`--stt`、`--tts`、`--llm_backend` 的启动 argv。容量不足或队列非空必须保持阻塞，不取消或重启未知任务。

## 回执与准入

1. 通过真实 Realtime 客户端完成一回合，保存回复音频及量测 JSON（识别文本、回复文本、`zh|ja`、首音频/完整响应延迟）。
2. `aifilm speech-preview session` 完整解码音频，写入带音频 SHA-256、模型锁与延迟的 candidate-only 回执。
3. `export-candidate` 产生“待人工试听”证据。中文旁白、日文女性、日文男性各至少两回合，人工确认语言分轨与可懂度。

任何回执都不能批准 production、改变默认 provider 或成为 final 音轨。
