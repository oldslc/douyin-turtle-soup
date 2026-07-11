"""
CosyVoice3 / Edge TTS 双引擎封装
支持懒加载 CosyVoice3，内建 Edge TTS 轻量引擎。
"""

import io
import sys
import os
from pathlib import Path

_cosyvoice_engine = None
_spk_registered = False

COSYVOICE_DIR = Path(__file__).resolve().parent / "CosyVoiceV7"
PROMPT_TEXT = "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"
PROMPT_WAV = "zero_shot_prompt.wav"
DEFAULT_SPK_ID = "default"

# ── Edge TTS ──
EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
EDGE_RATE = "+0%"
EDGE_VOLUME = "+0%"

# 中文发音人列表
EDGE_CN_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 (女声·推荐)",
    "zh-CN-XiaoyiNeural": "晓伊 (女声·情感)",
    "zh-CN-YunxiNeural": "云希 (男声)",
    "zh-CN-YunjianNeural": "云健 (男声)",
    "zh-CN-XiaohanNeural": "晓涵 (女声·温柔)",
    "zh-CN-XiaomengNeural": "晓梦 (女声·活泼)",
    "zh-CN-XiaochenNeural": "晓辰 (女声·知性)",
    "zh-CN-XiaomoNeural": "晓墨 (女声·文学)",
    "zh-CN-XiaoruiNeural": "晓睿 (女声·成熟)",
    "zh-CN-XiaoshuangNeural": "晓双 (女声·元气)",
    "zh-CN-XiaoxuanNeural": "晓萱 (女声·亲和)",
    "zh-CN-XiaoyanNeural": "晓颜 (女声·自然)",
    "zh-CN-XiaozhenNeural": "晓珍 (女声·温柔)",
    "zh-CN-YunyangNeural": "云扬 (男声·阳光)",
    "zh-CN-YunyeNeural": "云野 (男声·随性)",
    "zh-CN-YunfanNeural": "云帆 (男声·深沉)",
    "zh-CN-YunhaoNeural": "云皓 (男声·活力)",
}


def list_edge_voices() -> dict:
    """返回 {voice_id: display_name}"""
    return dict(EDGE_CN_VOICES)


def _add_cuda_dlls_to_path():
    """将 pip 安装的 nvidia CUDA 库 DLL 目录加入 PATH，供 onnxruntime 使用。"""
    site_packages = Path(__file__).resolve().parent.parent / "Lib" / "site-packages"
    nvidia_dir = site_packages / "nvidia"
    if not nvidia_dir.exists():
        site_packages = Path(os.__file__).resolve().parent / "site-packages"
        nvidia_dir = site_packages / "nvidia"
    if not nvidia_dir.exists():
        return False
    found = []
    for pkg_name in ["cuda_runtime", "cublas", "cudnn", "cufft", "cusparse", "cuda_nvrtc", "nvjitlink"]:
        bin_dir = nvidia_dir / pkg_name / "bin"
        if bin_dir.exists():
            found.append(str(bin_dir.resolve()))
    if not found:
        return False
    os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")
    return True


# ==================== CosyVoice3 ====================

def _load_cosyvoice():
    global _cosyvoice_engine, _spk_registered
    if _cosyvoice_engine is not None:
        return _cosyvoice_engine

    _add_cuda_dlls_to_path()

    matcha = str(COSYVOICE_DIR / "third_party" / "Matcha-TTS")
    if matcha not in sys.path:
        sys.path.insert(0, matcha)
    cv = str(COSYVOICE_DIR)
    if cv not in sys.path:
        sys.path.insert(0, cv)

    from cosyvoice.cli.cosyvoice import AutoModel

    model_dir = COSYVOICE_DIR / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    _cosyvoice_engine = AutoModel(model_dir=str(model_dir), fp16=True)
    print("[TTS] CosyVoice3 engine loaded")

    # 扫描注册 asset 目录下所有 WAV 文件（排除 cross_lingual_prompt.wav）
    asset_dir = COSYVOICE_DIR / "asset"
    _spk_registered = False
    if asset_dir.exists():
        registered = 0
        for f in sorted(asset_dir.glob("*.wav")):
            if f.name == "cross_lingual_prompt.wav":
                continue
            spk_id = "default" if f.stem == "zero_shot_prompt" else f.stem
            try:
                _cosyvoice_engine.add_zero_shot_spk(PROMPT_TEXT, str(f), spk_id)
                print(f"[TTS] Speaker '{spk_id}' registered from {f.name}")
                registered += 1
                _spk_registered = True
            except Exception as ex:
                print(f"[TTS] Failed to register {f.name}: {ex}")
        if registered == 0:
            print(f"[TTS] WARNING: No valid .wav files in {asset_dir}")
    else:
        print(f"[TTS] WARNING: {asset_dir} not found")
    return _cosyvoice_engine


def cosyvoice_status() -> dict:
    """返回 CosyVoice3 详细状态字典。"""
    # 1. 检查目录是否存在
    if not COSYVOICE_DIR.exists():
        return {"status": "not_found", "label": "CosyVoice3", "detail": "CosyVoice 目录不存在"}
    # 2. 检查能否导入关键依赖（不加载模型）
    try:
        import torch
        import onnxruntime
    except ImportError:
        return {"status": "deps_missing", "label": "CosyVoice3", "detail": "依赖未安装 (torch/onnxruntime)"}
    # 3. 检查模型文件是否齐全（推理实际需要的文件）
    model_dir = COSYVOICE_DIR / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    # spk2info.pt 可选（运行时自动生成），不在必需列表中
    required = ["llm.pt", "flow.pt", "hift.pt", "campplus.onnx", "speech_tokenizer_v3.onnx"]
    missing = [f for f in required if not (model_dir / f).exists()]
    # 检查 CosyVoice-BlankEN 目录（Qwen tokenizer）
    if not (model_dir / "CosyVoice-BlankEN").is_dir():
        missing.append("CosyVoice-BlankEN/ (tokenizer 目录)")
    else:
        for bf in ["model.safetensors", "config.json", "vocab.json", "tokenizer_config.json", "merges.txt", "generation_config.json"]:
            if not (model_dir / "CosyVoice-BlankEN" / bf).exists():
                missing.append(f"CosyVoice-BlankEN/{bf}")
    if missing:
        dir_detail = ""
        if model_dir.exists():
            dir_detail = f" 目录内容: {os.listdir(str(model_dir))}"
        return {"status": "model_missing", "label": "CosyVoice3", "detail": f"模型文件缺失: {missing}{dir_detail}"}
    # 4. 尝试完整加载
    try:
        eng = _load_cosyvoice()
        if _spk_registered:
            # 附加模型文件大小信息
            total_bytes = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
            size_info = f"{total_bytes / (1024**3):.1f} GB" if total_bytes > 0 else "?"
            return {"status": "ready", "label": "CosyVoice3", "detail": f"已就绪 (模型大小: {size_info})"}
        return {"status": "error", "label": "CosyVoice3", "detail": "说话人注册失败"}
    except Exception as e:
        return {"status": "error", "label": "CosyVoice3", "detail": f"加载失败: {str(e)[:60]}"}


def cosyvoice_available() -> bool:
    return cosyvoice_status()["status"] == "ready"


def reset_cosyvoice():
    """清除 CosyVoice3 缓存，强制下次调用时重新加载。部署后调用。"""
    global _cosyvoice_engine, _spk_registered
    _cosyvoice_engine = None
    _spk_registered = False


def list_cosyvoice_speakers() -> dict:
    """返回 {spk_id: {"name": display_name}} 字典。"""
    try:
        eng = _load_cosyvoice()
        if eng is None or not _spk_registered:
            return {}
        return {
            sid: {"name": "默认音色" if sid == DEFAULT_SPK_ID else sid}
            for sid in eng.frontend.spk2info.keys()
        }
    except Exception:
        return {}


def register_cosyvoice_speaker(spk_id: str, prompt_wav_path: str) -> bool:
    """注册一个新的零样本说话人。"""
    try:
        eng = _load_cosyvoice()
        if eng is None:
            return False
        eng.add_zero_shot_spk(PROMPT_TEXT, prompt_wav_path, spk_id)
        global _spk_registered
        _spk_registered = True
        return True
    except Exception as e:
        print(f"[TTS] Register speaker failed: {e}")
        return False


def remove_cosyvoice_speaker(spk_id: str) -> bool:
    """删除一个已注册的说话人（不允许删除 default）。"""
    if spk_id == DEFAULT_SPK_ID:
        print(f"[TTS] Cannot remove default speaker")
        return False
    removed = False
    try:
        # 从引擎中移除（如果已加载）
        eng = _load_cosyvoice()
        if eng is not None and spk_id in eng.frontend.spk2info:
            del eng.frontend.spk2info[spk_id]
            removed = True
    except Exception as e:
        print(f"[TTS] Remove from engine failed (non-fatal): {e}")
    # 删除对应的 WAV 文件（即使引擎未加载）
    try:
        asset_dir = COSYVOICE_DIR / "asset"
        for wav_path in [asset_dir / f"{spk_id}.wav", asset_dir / f"zero_shot_prompt_{spk_id}.wav"]:
            if wav_path.exists():
                wav_path.unlink()
                print(f"[TTS] Deleted speaker file: {wav_path}")
                removed = True
    except Exception as e:
        print(f"[TTS] Delete file failed: {e}")
    if removed:
        print(f"[TTS] Speaker '{spk_id}' removed")
    return removed


def cosyvoice_generate(text: str, spk_id: str = DEFAULT_SPK_ID) -> tuple:
    """Return (sample_rate, wav_bytes) or (None, None) on failure. spk_id 选择说话人。"""
    import soundfile as sf

    try:
        eng = _load_cosyvoice()
        if not _spk_registered:
            return None, None
        # 如果指定的 spk_id 不存在则回退到第一个可用说话人
        if spk_id not in eng.frontend.spk2info:
            spk_ids = list(eng.frontend.spk2info.keys())
            spk_id = spk_ids[0] if spk_ids else DEFAULT_SPK_ID
            if spk_id not in eng.frontend.spk2info:
                return None, None
        buf = io.BytesIO()
        for j in eng.inference_zero_shot(
            text, PROMPT_TEXT,
            str(COSYVOICE_DIR / "asset" / PROMPT_WAV),
            zero_shot_spk_id=spk_id,  # 非空时 frontend 用缓存的 spk2info，忽略 prompt_wav
            stream=False,
        ):
            sf.write(buf, j["tts_speech"].squeeze().cpu().numpy(), eng.sample_rate, format="WAV")
        buf.seek(0)
        return eng.sample_rate, buf.read()
    except Exception as e:
        print(f"[TTS] CosyVoice3 error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ==================== Edge TTS ====================

def edge_available() -> bool:
    try:
        import edge_tts
        return True
    except ImportError:
        return False


async def edge_generate_async(text: str, voice: str = None, rate: float = None) -> tuple:
    """Return (sample_rate, mp3_bytes) — Edge TTS 输出 MP3."""
    import edge_tts
    # rate: float → edge-tts 格式 "+XX%" / "-XX%"
    rate_str = EDGE_RATE  # 纯客户端调速，服务端始终 +0%
    communicate = edge_tts.Communicate(
        text, voice=voice or EDGE_VOICE,
        rate=rate_str, volume=EDGE_VOLUME,
    )
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    return 24000, audio


def edge_generate(text: str) -> tuple:
    """同步包裹，返回 (24000, mp3_bytes)"""
    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            # 已经在 async 上下文中，用 run_coroutine_threadsafe
            import concurrent.futures
            new_loop = asyncio.new_event_loop()
            try:
                result = new_loop.run_until_complete(edge_generate_async(text))
                return result
            finally:
                new_loop.close()
        else:
            return asyncio.run(edge_generate_async(text))
    except Exception as e:
        print(f"[TTS] Edge TTS error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


# ==================== 统一入口 ====================

async def async_generate_speech(text: str, engine: str = "cosyvoice", voice: str = None, rate: float = None, spk_id: str = None) -> tuple:
    """
    异步统一入口。Server 端 await 此函数。
    Edge TTS 直接 await，CosyVoice3 用 run_in_executor 避免阻塞。
    """
    import asyncio
    if engine == "edge":
        return await edge_generate_async(text, voice, rate)
    else:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: cosyvoice_generate(text, spk_id or DEFAULT_SPK_ID))


ENGINES = {
    "cosyvoice": {"label": "CosyVoice3", "available": cosyvoice_available, "generate": cosyvoice_generate},
    "edge": {"label": "Edge TTS", "available": edge_available, "generate": edge_generate},
}


def list_engines() -> dict:
    """返回 {engine_id: {"label": ..., "available": bool, "status": str, "detail": str}}"""
    cv = cosyvoice_status()
    return {
        "cosyvoice": {
            "label": cv["label"], "available": cv["status"] == "ready",
            "status": cv["status"], "detail": cv["detail"],
        },
        "edge": {
            "label": "Edge TTS", "available": edge_available(),
            "status": "ready" if edge_available() else "deps_missing", "detail": "",
        },
    }


def generate_speech(text: str, engine: str = "cosyvoice") -> tuple:
    """
    统一入口。
    Returns (sample_rate, audio_bytes) or (None, None).
    CosyVoice3 → WAV, Edge TTS → MP3.
    """
    info = ENGINES.get(engine)
    if info is None:
        print(f"[TTS] Unknown engine: {engine}")
        return None, None
    return info["generate"](text)


def is_available(engine: str = "cosyvoice") -> bool:
    info = ENGINES.get(engine)
    if info is None:
        return False
    return info["available"]()
