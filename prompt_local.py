"""Local prompt planning with an execution-scoped Transformers model."""

from contextlib import contextmanager
from functools import partial
import gc
import logging
import os
from pathlib import Path
import time
import traceback

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText, AutoProcessor, AutoTokenizer, BitsAndBytesConfig, StoppingCriteria
from transformers.image_utils import load_image
from transformers.models.auto.modeling_auto import MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES

import comfy.model_management
import comfy.model_patcher
import folder_paths
from comfy_api.latest import io

from .prompt_planner import plan_prompts

_LOG = logging.getLogger("h3_motion_context")
folder_paths.add_model_folder_path("LLM", str(Path(folder_paths.models_dir) / "LLM"))
_DTYPES = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}


def local_model_names():
    names = set()
    for directory in folder_paths.get_folder_paths("LLM"):
        root = Path(directory)
        for config in root.rglob("config.json"):
            if ".cache" not in config.relative_to(root).parts:
                names.add(config.parent.relative_to(root).as_posix())
    return sorted(names)


def local_model_path(name):
    for directory in folder_paths.get_folder_paths("LLM"):
        root = Path(directory).resolve()
        path = (root / name).resolve()
        if path.is_relative_to(root) and (path / "config.json").is_file():
            return path
    raise FileNotFoundError("Local prompt model not found inside models/LLM. Select a local Transformers model folder.")


class PromptStoppingCriteria(StoppingCriteria):
    def __init__(self, timeout_seconds):
        self.deadline = time.monotonic() + timeout_seconds

    def __call__(self, input_ids, scores, **kwargs):
        comfy.model_management.throw_exception_if_processing_interrupted()
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Local prompt generation timed out. Increase timeout_seconds or select a smaller model.")
        return False


def local_response(text, prompt_tokens, completion_tokens, truncated):
    text = "" if "<think>" in text and "</think>" not in text else text.rsplit("</think>", 1)[-1].strip()
    message = {"role": "assistant", "content": text}
    return {
        "choices": [{"message": message, "finish_reason": "length" if truncated else "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
    }


def request_local(model, tokenizer, device, timeout_seconds, payload, processor=None):
    comfy.model_management.throw_exception_if_processing_interrupted()
    if processor is not None:
        messages = [{**m, "content": [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else m["content"]} for m in payload["messages"]]
        images = [load_image(part["image_url"]["url"]) for m in messages for part in m["content"] if part["type"] == "image_url"]
        text = processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=False, enable_thinking=False)
        inputs = processor(text=[text], images=images, return_tensors="pt").to(device)
    else:
        inputs = tokenizer.apply_chat_template(
            payload["messages"], add_generation_prompt=True, tokenize=True,
            enable_thinking=False, return_dict=True, return_tensors="pt").to(device)
    prompt_tokens = inputs["input_ids"].shape[-1]
    output = model.generate(
        **inputs, max_new_tokens=payload["max_tokens"], do_sample=False, return_dict_in_generate=False,
        stopping_criteria=[PromptStoppingCriteria(timeout_seconds)],
        pad_token_id=tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id)
    completion = output[0, prompt_tokens:]
    eos = model.generation_config.eos_token_id
    eos = eos if isinstance(eos, list) else [eos]
    truncated = len(completion) >= payload["max_tokens"] and int(completion[-1]) not in eos
    text = tokenizer.decode(completion, skip_special_tokens=True)
    comfy.model_management.throw_exception_if_processing_interrupted()
    return local_response(text, prompt_tokens, len(completion), truncated)


@contextmanager
def local_prompt_request(model_name, device="auto", dtype="auto", free_vram_before_load=True,
                         timeout_seconds=600, quantization="none", with_images=False):
    path = local_model_path(model_name)
    load_device = comfy.model_management.get_torch_device() if device == "auto" else torch.device("cpu")
    if device not in ("auto", "cpu") or dtype not in ("auto", *_DTYPES):
        raise ValueError("Unsupported local prompt device or dtype.")
    if quantization not in ("none", "nf4"):
        raise ValueError("Unsupported local prompt quantization.")
    compute_dtype = (torch.float32 if load_device.type == "cpu" else "auto") if dtype == "auto" else _DTYPES[dtype]
    comfy.model_management.throw_exception_if_processing_interrupted()
    config = AutoConfig.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True, trust_remote_code=False)
    if not tokenizer.chat_template:
        raise ValueError("Local prompt model needs an instruction chat template.")
    model_class = AutoModelForImageTextToText if config.model_type in MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES else AutoModelForCausalLM
    if with_images and model_class is AutoModelForCausalLM:
        raise ValueError("所选本地模型不支持识图。请选择 Qwen-VL 等视觉模型，或关闭“AI 识别参考图”。")
    processor = AutoProcessor.from_pretrained(path, local_files_only=True, trust_remote_code=False) if with_images else None
    model = None
    patcher = None
    request = None
    try:
        if free_vram_before_load and load_device.type != "cpu":
            comfy.model_management.free_memory(1e30, load_device)
            comfy.model_management.soft_empty_cache()
        _LOG.info("H3 Prompt Local: loading %s on %s", model_name, load_device)
        load_options = {}
        if quantization == "nf4":
            quant_dtype = (torch.float32 if load_device.type == "cpu" else torch.bfloat16) if dtype == "auto" else _DTYPES[dtype]
            load_options = {
                "device_map": {"": load_device},
                "quantization_config": BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=quant_dtype),
            }
            compute_dtype = quant_dtype
        async_load = os.environ.get("HF_DEACTIVATE_ASYNC_LOAD")
        try:
            if quantization == "nf4":
                # Transformers 5.3 otherwise queues full-precision GPU copies before quantization.
                os.environ["HF_DEACTIVATE_ASYNC_LOAD"] = "1"
            model = model_class.from_pretrained(
                path, config=config, local_files_only=True, trust_remote_code=False,
                dtype=compute_dtype, attn_implementation="sdpa", **load_options)
        finally:
            if quantization == "nf4":
                if async_load is None:
                    os.environ.pop("HF_DEACTIVATE_ASYNC_LOAD", None)
                else:
                    os.environ["HF_DEACTIVATE_ASYNC_LOAD"] = async_load
        if quantization == "none":
            # Transformers exposes a read-only device property; ComfyUI owns this wrapper's device.
            patcher = comfy.model_patcher.ModelPatcher(torch.nn.ModuleList([model]), load_device, torch.device("cpu"))
            comfy.model_management.load_models_gpu([patcher], force_full_load=True)
        comfy.model_management.throw_exception_if_processing_interrupted()
        request = partial(request_local, model, tokenizer, load_device, timeout_seconds, processor=processor)
        yield request
    except BaseException as error:
        # Generation tracebacks otherwise retain GPU activations/KV cache after cancellation.
        traceback.clear_frames(error.__traceback__)
        raise
    finally:
        if patcher is not None:
            comfy.model_management.unload_model_and_clones(patcher)
            # Also offload a partially loaded model if loading failed before registration.
            patcher.unpatch_model(torch.device("cpu"))
        elif model is not None:
            model.to("cpu")
        request = model = patcher = None
        gc.collect()
        comfy.model_management.cleanup_models()
        comfy.model_management.soft_empty_cache()
        _LOG.info("H3 Prompt Local: unloaded %s", model_name)


def split_local_prompts(prompt, schedule, input_mode, reference_image_count, model_name,
                        device="auto", dtype="auto", free_vram_before_load=True,
                        max_tokens=16384, timeout_seconds=600, variation=0, log_prompts=True, quantization="none"):
    with local_prompt_request(model_name, device, dtype, free_vram_before_load, timeout_seconds, quantization) as request:
        return plan_prompts(prompt, schedule, input_mode, reference_image_count,
                            model_name, variation, request, False, max_tokens, log_prompts)


class MiniMaxH3PromptLocal(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PromptLocal",
            display_name="H3 Prompt Local",
            category="video/minimax",
            description="Use a local Transformers instruction model to write concise clip prompts as JSON; no tool calling required. Loads only during multi-segment prompt planning and always unloads before H3 encoding/sampling, including on failure or cancellation. No downloads or API server.",
            inputs=[
                io.Combo.Input("model_name", options=local_model_names(),
                    tooltip="Local model folder under models/LLM (including extra_model_paths.yaml LLM roots). Requires config, tokenizer and model weights; for example Qwen3-VL-4B-Instruct. GGUF is not supported."),
                io.Combo.Input("device", options=["auto", "cpu"], default="auto",
                    tooltip="auto uses ComfyUI's current device. cpu keeps this language model off the GPU but runs more slowly."),
                io.Boolean.Input("free_vram_before_load", default=True,
                    tooltip="Offload ComfyUI models on the selected GPU before loading the language model. They reload when needed for video. The language model is always unloaded after prompt planning."),
                io.Combo.Input("dtype", options=["auto", "bfloat16", "float16", "float32"], default="auto", optional=True, advanced=True),
                io.Int.Input("max_tokens", default=16384, min=1, max=131072, optional=True, advanced=True),
                io.Int.Input("timeout_seconds", default=600, min=1, max=3600, optional=True, advanced=True,
                    tooltip="Time limit per text generation; checked after each generated token. Model loading is not included."),
                io.Int.Input("variation", default=0, min=0, max=0x7fffffff, optional=True, advanced=True),
                io.Boolean.Input("log_prompts", default=True, optional=True, advanced=True),
                io.Combo.Input("quantization", options=["none", "nf4"], default="none", optional=True,
                    tooltip="nf4 loads existing unquantized weights in 4-bit using bitsandbytes, reducing VRAM use without changing the files. Use this for a 9B model on a 16GB GPU. Keep free_vram_before_load enabled; quantized loading is managed by Transformers."),
            ],
            outputs=[io.Custom("H3_PROMPT_API").Output(display_name="prompt_api")],
        )

    @classmethod
    def execute(cls, model_name, device="auto", free_vram_before_load=True, dtype="auto",
                max_tokens=16384, timeout_seconds=600, variation=0, log_prompts=True, quantization="none"):
        return io.NodeOutput({
            "backend": "local", "model_name": model_name, "device": device, "dtype": dtype,
            "free_vram_before_load": free_vram_before_load, "max_tokens": max_tokens,
            "timeout_seconds": timeout_seconds, "variation": variation, "log_prompts": log_prompts,
            "quantization": quantization,
        })


NODE_CLASS_MAPPINGS = {"MiniMaxH3PromptLocal": MiniMaxH3PromptLocal}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3PromptLocal": "H3 Prompt Local"}
