"""Editable Ref2VA fields and locally selected reference pictures."""

import base64
import hashlib
from io import BytesIO
import json
import logging
import re
import sys
import time

import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn.functional as F

import folder_paths
from comfy_api.latest import io

from .prompt_local import local_prompt_request
from .prompt_log import new_prompt_log_path, prompt_request_log, prompt_trace_text, write_prompt_log
from .prompt_planner import chat_endpoint, read_json_message, request_chat

FIELDS = (
    "subject_definitions", "summary", "retention_analysis", "detailed_description",
    "overall_soundscape", "non_diegetic_music",
)
LABELS = ("主体定义", "内容概述", "参考保留规则", "画面与动作时间线", "整体环境声", "背景音乐")
_LOG = logging.getLogger("h3_motion_context")
SYSTEM_PROMPT = """你是 MiniMax H3 Ref2VA 提示词编辑。忠实保留用户要求，结合参考图片写出六段可执行提示词。
输入的 fields 可能已有六段内容，也可能只有 detailed_description 放着整篇普通描述。
先在内部确认原文的事件顺序、每段起止时间、说话者与台词、情绪、指定镜头，
并区分贯穿场景的环境底声与只在某个动作或地点出现的声音，再写正文。
优先级：用户明确要求 > 对白完整与时间安排 > 图片身份和场景特征 > 补充的拍摄细节。
没有动作安排的简短想法，可补充自然动作与画面；已有定时对白或动作时，围绕原有事件
补齐构图、人物位置、视线、光线和参考关系，不另编一套动作流程，不为追求篇幅增加事件。
只输出一个 JSON 对象，恰好包含六个字符串字段：subject_definitions、summary、
retention_analysis、detailed_description、overall_soundscape、non_diegetic_music。
不要输出 Markdown 代码块、解释或工具调用，字段值内不要重复六段标题。

保持原文语言：中文输入的六个字段均使用中文描述，英文输入使用英文；不要翻译台词，
不要附加台词译文。保留用户明确指定的人物、服装、动作、景别、运镜、情绪和时间。
情绪用原文的词明确写出，不改变情绪性质，不用额外表演改变语义，例如惊讶不等于惊喜。
只补充与原文相容的少量微动作、构图和光线；声音按下文的声源与时间规则处理。不要添加剧情、人物关系、
转折、台词或背景音乐。未指定运镜时采用简单稳定的摄影安排，不同时堆叠多种运镜。
图片紧跟各自的 <Picture N> 标签。确实收到图片时，观察可见的外貌、服装、道具、
场景布局与光线；把观察结果写进主体定义和镜头描述，不能只输出“一男”“一女”“餐厅”。
先核对多个视角中一致可见的结构，再命名发型和服装；卷发、编发、发饰不能凭轮廓猜成
马尾或发髻，外层衣摆与内层裤装分别观察颜色。看不清的结构只写能确认的特征，
不把猜测补成确定事实，也不在 retention_analysis 中反复强化未确认的特征。
角色多视图展示的是同一人的不同角度，不要生成多个分身，也不要照搬拼图分栏和灰底。
人物参考用于身份与服装，场景参考用于布景和灯光。文字明确要求的变化优先于图片。
未收到图片像素时只能根据文字定义，不声称看过图片。只引用提供的 <Picture N>，
不猜测被遮挡或看不清的细节，不从外貌推断人物姓名、背景或关系。

subject_definitions：用 <Subject N> 定义需要追踪的人物、场景等，每项一行；
保留已有主体编号。每个来自图片的主体必须在同一行明确写出实际来源，例如
“<Subject 3> 道具（来源：<Picture 5>）：可辨认的外形、颜色和结构。”
主体编号和图片编号独立，不能默认同号对应。原文“图5”等写法转换成 <Picture 5>，
按原文指定的来源绑定，不能因重新排列主体而改变图片编号。多图定义同一主体时列出各自作用；
同一图可以提供多个主体。只有图片来源而无独立关键帧用途时，不另建 <Picture N> 条目。
仅绑定实际使用且已提供的图片；没有图片来源的纯文字主体不虚构绑定。
写清可辨认的外观、衣着或环境特征，来源标签不能代替外观描述。
每项包含实际描述，不能仅填写一个编号。人物身份参考描述稳定特征，不把照片中的
微笑、拍摄姿势或视线写成身份的一部分；原文明确参考表情或姿势时例外。
summary：用一句简短的话概述视频，不引用台词原句，用概括性叙述表达事件。以 [reference generation] 开头；
原文明确使用首帧或关键帧时用 [keyframe completion + reference generation]，保留已有适用前缀。
概述使用已有 <Subject N> 表明主要人物和场景。
retention_analysis：按已定义的引用标签逐行写“<Subject N>（出现于 [Shot N]）：
fully_preserved - 要保留的具体特征”。只有原文改变了该引用的既定特征时才用
partially_preserved；特征转移到其他主体时用 attribute_transfer；仅借鉴大致风格时用
weak_reference。人物正常说话、动作和表情变化不代表损失身份保真，不为此单列标记；
图片未提供的信息不属于 weak_reference。不冻结姿势、视线或表情。
这里只分析从素材保留的特征，不把新编排的座位、目标动作或后续情绪当成参考特征；
这些内容放入 detailed_description。出现镜头只列实际可见的镜头，面部近景未展示的另一人不列入。

detailed_description：先用一两句建立视觉风格与共同环境，再逐镜头写。
沿用参考图的视觉质感，交代景别、构图、主体位置和朝向、原文动作与表情、摄影和声音。
重要主体在镜头首次出现时带上对应的 <Subject N>，与主体定义的图片来源保持一致。
多人同乘、行走或飞行时，交代人物前后或左右顺序、面向、载具前端与运动方向，
连续运动保持这些关系；跟拍用环境视差或衣发运动体现前进，不擅自绕到运动轴另一侧。
从站立到坐下、从远处到接触物品等已明确的状态变化，补出必要的最短动作衔接。
“合作化解”“获得物品”等概述需落实为可见互动和结果，在原有时间范围内完成，
不另加任务、冲突、道具或对白；用户已给出具体过程时照原过程写，不替换成另一套动作。
补充具体且必要的画面信息，避免“未指定”“同上”、文学比喻、冗长装饰或反复描写布景。
[Shot 1] 表示开场，后面不写 At 时间戳。镜头标记单独起段，先写镜头建立，再写所属事件时间段。
时间段和镜头是两回事：说话者改变、下一个时间段开始都不自动切镜。
原文要求切镜、切换到另一地点或明确换镜头时，增加 [Shot N] At MM:SS.mmm, ...，时间戳后保留逗号。
连续移动、绕到人物背后、拉远等运镜及其景别变化仍属于当前镜头，不为它们另起 [Shot N]。
保留原始切镜时刻、场景灯光和人物视线连续性，不因切镜改变主光方向。
没有指定换镜头或切换地点时保持同一镜头；明确要求连续镜头时不切镜。
同一连续镜头中的人物位置前后一致；后文明确了并肩等关系而前文未指定时，从开场就采用相容位置，
不先安排相对而坐再无动作地变成并肩，也不为补写的布局增加换座或转身动作。
镜头时间戳不能替代事件时间范围：原文每个范围必须在正文中作为单独的“起–止 秒：”段保留，
每个时间段另起一段，可把 s 统一为 秒，但起止数值与对应事件不变；即使某个范围与整个镜头重合也必须写出。
多个事件时间段可以归属同一个 [Shot N]。没有给定时间时不要凭空编号秒数。

定时对白先核定说话所需时间，再补不挤占对白的动作。正文仍按原文事件先后叙述：
若原文是先出现表情再说话，就先写这一表情变化，紧接说话者与台词；不要把台词放在
段首后才补叙之前发生的动作或情绪。原台词逐字保留且只在所属时间段的 <d> 中出现一次。
普通话写成“<Subject N> (Sx) 说：<d>[Chinese] 原台词。</d>”；实际说话顺序决定稳定的
(S1)、(S2)，同一人继续沿用；保留原有语言标签。完整句末加标点，放在 </d> 前。
保持原文要求的动作顺序；只要求情绪加说话时，让表情简短变化后及时开口，
不要擅自添加取放物品、点头、转身、长时间停顿等前置动作来推迟台词。
对白期间至多补一个不占额外时间的简单神态，听者保持安静。
最后一句应在所属区间内完整说完，正文明确写在该区间结束前留短暂闭口反应，避免最后一个字贴在视频终点。
允许在原区间内部安排细分节拍，但原范围必须仍作为段首保留，不擅自延长总时长或移动对白。
若原文要求说到结束或故意截断，则遵循原文。不要承诺生成模型能精确按秒执行。

声音先尊重原文：保留明确要求的音效、静音和跨镜头延续。未指定声音时，可用一句简短、
低音量的场景底声描述；不必为每个可见物体、微动作配音，也不要为了填满字段罗列音效。
局部音效只取自原文明确要求的声音或直接可闻的动作，例如拍手、敲门；轻轻搅动、看向对方等
未明确要求声音的轻微动作保留为视觉描述，不擅自添加敲击、碰撞或接触来制造音效。
静态图片只提供视觉依据，不证明声源正在发声。冒热气不等于沸腾，看到火焰不等于持续噼啪，
云雾流动不等于水声，人物呼吸不等于可闻喘息；原文未要求时不要据此补出这些声音。
overall_soundscape：只写适用于整片的环境底声与总体听感，保持对白清晰；没有共同底声可填 None。
不把不同地点的声音汇总成同时持续的背景声，不重复台词、动作音效或各镜头的声音清单。
仅属于某地点的环境声、同步动作音效和非语言人声放在 detailed_description 的对应时间段，
写清声源、触发动作及停止点，音量与景别、距离相符；动作结束或离开该地点时结束，除非原文要求延续。
已有 overall_soundscape 混入局部声音时，将其移到对应动作段，保持用户要求的声音及其时间范围。
例如：原文只有厨房搅锅、热气升起，保留这两个视觉动作，不自动补出沸腾、气泡炸裂或炉火噼啪声。
若原文明示 3–6 秒厨房内有炉火声，则只写进 3–6 秒段，6 秒离开厨房时结束，不放入 overall_soundscape。
生成正文用简短的正面描述表达需要的声音，不输出上述禁用声音清单，也不逐镜头重复“无某某声”。
non_diegetic_music：只描述背景音乐；原文未要求音乐时填写 None。没有内容的可选段可留空。

返回前逐条与原文对照：六个值都是字符串，语言不变，每个原时间范围都明确保留，
每段原有动作未被静态构图代替，对应说话者与台词不变，情绪不变，没有额外切镜、前置动作或剧情，末句有收尾空间，
逐项核对图片来源：原文指定的每个图与主体关系都在 subject_definitions 中明确保留，
不能只留下 <Subject N> 而删掉其 <Picture N>，各段外观与来源图相符且不互相矛盾；
[Shot 1] 无时间戳，后续镜头时刻与原文一致，连续运镜未变成切镜；
全局声场没有局部音效，每个局部声音都有原文或明确动作依据及起止范围，没有从图片臆测持续声响。
"""


def picture_paths(pictures):
    names = json.loads(pictures)
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("图片列表必须是文件名数组。请重新选择图片。")
    return [folder_paths.get_annotated_filepath(name) for name in names]


def load_pictures(paths):
    images = []
    for path in paths:
        with Image.open(path) as image:
            rgb = ImageOps.exif_transpose(image).convert("RGB")
            images.append(torch.from_numpy(np.array(rgb).astype(np.float32) / 255.0))
    if not images:
        return None
    height = max(image.shape[0] for image in images)
    width = max(image.shape[1] for image in images)
    # IMAGE batches need equal dimensions; padding keeps every reference uncropped.
    padded = []
    for image in images:
        dh, dw = height - image.shape[0], width - image.shape[1]
        padded.append(F.pad(image, (0, 0, dw // 2, dw - dw // 2, dh // 2, dh - dh // 2)))
    return torch.stack(padded)


def assemble_prompt(fields):
    return "\n\n".join(f"{name}:\n{fields[name]}" for name in FIELDS)


def picture_content(paths):
    content, metadata = [], []
    for index, path in enumerate(paths):
        label = f"<Picture {index + 1}>"
        with Image.open(path) as source:
            rgb = ImageOps.exif_transpose(source).convert("RGB")
            original_size = rgb.size
            rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            rgb.save(buffer, format="JPEG", quality=85)
        jpeg = buffer.getvalue()
        content.extend([
            {"type": "text", "text": label},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")}},
        ])
        metadata.append({"label": label, "path": str(path), "original_size": original_size, "sent_size": rgb.size, "jpeg_bytes": len(jpeg)})
    return content, metadata


def save_builder_log(fields, result, pictures, model, elapsed, responses, api_key,
                     payload=None, path=None, error=None):
    requests = [prompt_request_log(payload, "H3 fields")] if payload else []
    report = {"operation": "ai_rewrite" if payload else "builder_output",
              "model": model, "elapsed_seconds": round(elapsed, 3), "pictures": pictures,
              "source_fields": fields, "result_fields": result, "responses": responses,
              "requests": requests, "final_prompt": assemble_prompt(result) if result is not None else None,
              "error": f"{type(error).__name__}: {error}" if error else None,
              "status": "ok" if result is not None else "failed"}
    text = (f"Model: {model}\nElapsed: {elapsed:.3f}s\nPictures:\n{json.dumps(pictures, ensure_ascii=False, indent=2)}\n\n"
            f"Original prompt:\n\n{assemble_prompt(fields)}\n\nFinal prompt:\n\n{report['final_prompt']}\n\n"
            f"{prompt_trace_text(requests, responses)}")
    if error:
        text += f"\n\nError: {report['error']}"
    return write_prompt_log(path or new_prompt_log_path("builder"), report, text, api_key)


def rewrite_fields(fields, picture_count, config, image_paths=(), log_path=None):
    content, pictures = picture_content(image_paths)
    source = json.dumps({"pictures": [f"<Picture {i + 1}>" for i in range(picture_count)],
                         "fields": fields, "variation": config.get("variation", 0)}, ensure_ascii=False)
    if content:
        content.append({"type": "text", "text": source})
    payload = {
        "model": config.get("model_name") if config.get("backend") == "local" else config["model"],
        "max_tokens": config.get("max_tokens", 4096), "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content or source},
        ],
    }
    started = time.monotonic()
    result, responses = None, []
    _LOG.info("H3 Prompt Builder: %s, %d images, %.1f KiB JPEG", payload["model"], len(pictures), sum(p["jpeg_bytes"] for p in pictures) / 1024)
    try:
        if config.get("backend") == "local":
            options = {key: config[key] for key in (
                "model_name", "device", "dtype", "free_vram_before_load", "timeout_seconds", "quantization"
            ) if key in config}
            with local_prompt_request(**options, with_images=bool(image_paths)) as request:
                data = request(payload)
        else:
            if config.get("json_mode", True):
                payload["response_format"] = {"type": "json_object"}
            key = config.get("api_key", "").strip()
            data = request_chat(chat_endpoint(config["api_url"]), payload,
                                {"Authorization": f"Bearer {key}"} if key else {}, config.get("timeout_seconds", 600))
        values = read_json_message(data, responses, "H3 fields")
        if not isinstance(values, dict) or any(not isinstance(values.get(name), str) for name in FIELDS):
            raise ValueError("AI 没有返回完整的六个文本字段。原文未改动，请重试或增加 max_tokens。")
        result = {name: values[name] for name in FIELDS}
        result["detailed_description"] = re.sub(
            r"(?m)^([ \t]*\[Shot [1-9]\d*\] At \d{2}:\d{2}\.\d{3})[，,]?", r"\1,", result["detailed_description"])
        return result
    finally:
        if config.get("log_prompts", True):
            save_builder_log(fields, result, pictures, payload["model"], time.monotonic() - started,
                             responses, config.get("api_key", ""), payload, log_path, sys.exception() if result is None else None)


class MiniMaxH3PromptBuilder(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PromptBuilder", display_name="H3 Ref Prompt Builder",
            category="video/minimax", is_output_node=True,
            description="Ref2VA 六段提示词与图片编辑器。直接填写即可使用；连接 H3 Prompt Local/API 后可点击 AI 整理。",
            inputs=[
                *[io.String.Input(name, default="None" if name == "non_diegetic_music" else "",
                                  multiline=True, tooltip=label) for name, label in zip(FIELDS, LABELS)],
                io.String.Input("pictures", default="[]"),
                io.Int.Input("ai_request", default=0, min=0, max=0x7fffffff),
                io.Custom("H3_PROMPT_API").Input("prompt_api", optional=True),
                io.Boolean.Input("ai_read_images", default=True, optional=True,
                                 tooltip="AI 读取压缩后的参考图。需要视觉模型；关闭后仅处理文字。"),
                io.Boolean.Input("log_prompts", default=True, optional=True,
                                 tooltip="保存原文、最终提示词和 AI 输入/回复到 output/h3_prompt_logs。连接的 Prompt Local/API 也需开启 log_prompts。"),
            ],
            outputs=[io.String.Output(display_name="prompt"), io.Image.Output(display_name="reference_images")],
        )

    @classmethod
    def fingerprint_inputs(cls, pictures="[]", **kwargs):
        digest = hashlib.sha256()
        for path in picture_paths(pictures):
            with open(path, "rb") as file:
                digest.update(hashlib.file_digest(file, "sha256").digest())
        return digest.hexdigest()

    @classmethod
    def execute(cls, subject_definitions, summary, retention_analysis, detailed_description,
                overall_soundscape, non_diegetic_music, pictures="[]", ai_request=0, prompt_api=None, ai_read_images=True,
                log_prompts=True):
        fields = dict(zip(FIELDS, (subject_definitions, summary, retention_analysis, detailed_description,
                                  overall_soundscape, non_diegetic_music)))
        paths = picture_paths(pictures)
        log_enabled = log_prompts and (prompt_api or {}).get("log_prompts", True)
        log_path = new_prompt_log_path("builder") if log_enabled else None
        if ai_request:
            if prompt_api is None:
                raise ValueError("请先连接 H3 Prompt Local 或 H3 Prompt API，再点击 AI 整理。手动填写无需 LLM。")
            fields = rewrite_fields(fields, len(paths), {**prompt_api, "log_prompts": log_enabled},
                                    paths if ai_read_images else (), log_path=log_path)
        prompt = assemble_prompt(fields)
        images = load_pictures(paths)
        if log_enabled and not ai_request:
            save_builder_log(fields, fields, [{"label": f"<Picture {i + 1}>", "path": str(path)} for i, path in enumerate(paths)],
                             None, 0, [], (prompt_api or {}).get("api_key", ""), path=log_path)
        return io.NodeOutput(prompt, images, ui={
            "h3_fields": [fields], "h3_prompt": [prompt], "h3_ai_request": [ai_request],
            "h3_log": [str(log_path.with_suffix(".txt"))] if log_path and log_path.with_suffix(".txt").is_file() else [],
        })


NODE_CLASS_MAPPINGS = {"MiniMaxH3PromptBuilder": MiniMaxH3PromptBuilder}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3PromptBuilder": "H3 Ref Prompt Builder"}
