# H3 Motion Context

[English](README.md)

一份提示词、一个总时长，生成 MiniMax H3 长视频。本项目 fork 自 [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)，新增自动采样、画面与音频续接、重叠裁剪、拼接，以及参考提示词编辑器和可选的 AI 提示词规划。原有续接节点继续保留。

## 安装与示例

需要 ComfyUI 支持原生 H3、任意关键帧锚点（ComfyUI 0.34.0+）和 **Concatenate Video**。长视频节点运行时也会检查原生视频拼接支持。

在 `ComfyUI/custom_nodes` 目录执行，然后重启 ComfyUI：

```sh
git clone https://github.com/ooizj/ComfyUI-H3-Motion-Context.git comfyui-h3-motion-context
```

同一节点包只保留一份安装，避免重复注册。已经安装时更新原目录，不要再克隆一份。更新前端文件后刷新浏览器。

打开 [H3 Long Video - Simple.json](example_workflows/H3%20Long%20Video%20-%20Simple.json)。这个最小示例包含 **H3 Model Loader → H3 Long Video (Simple) → Save Video**。选择本机模型，填写 `prompt` 和 `total_seconds` 后运行。要使用下图的参考图工作流，再从 `video/minimax` 分类添加提示词节点。

## 截图中的节点怎么连接

[![参考提示词编辑器、Prompt API 与长视频节点接线](docs/images/ref-prompt-builder.png)](docs/images/ref-prompt-builder.png)

| 输出端 | 输入端 | 用途 |
| --- | --- | --- |
| Model Loader：`MODEL`、`CLIP`、`VAE`、`AUDIO_VAE` | Long Video：`model`、`clip`、`vae`、`audio_vae` | H3 生成所需的四路模型 |
| Ref Prompt Builder：`prompt` | Long Video：`prompt` | 完整六段提示词；需要时先将文本控件转换为输入接口 |
| Ref Prompt Builder：`reference_images` | Long Video：`reference_images` | 与 `<Picture N>` 顺序一致的参考图 |
| Prompt API **或** Prompt Local：`prompt_api` | Builder：`prompt_api` | 可选，用于 AI 整理和 AI 导入 |
| 同一个 Prompt API/Local 输出 | Long Video：`prompt_api` | 可选，用于多段视频的提示词规划 |
| Load Image：`IMAGE` | Long Video：`first_frame` | 可选首帧，仅约束第一段的开场 |
| Long Video：`VIDEO` | Save Video：`video` | 保存拼接完成、带音频的视频 |
| Long Video：`prompt_preview` | 可选的文本显示节点 | 执行后查看各段提示词和时间范围 |

两个 `prompt_api` 接口负责不同操作。既要整理提示词又要自动分段改写，就连接两处；也可以只接其中一处或都不接。H3 的 `clip` 文本编码器与可选的提示词 LLM 是两套模型。

截图中的**分辨率选择器**是可选的外部节点，不由本插件提供。将它的整数输出连接 `width` / `height` 即可，也可以直接填写 Long Video 高级选项中的宽高。截图参数只是使用示例，不代表节点默认值。

### H3 Model Loader

**这是示例工作流里的子图，不是额外注册的节点。** 它把标准 ComfyUI 加载器组合在一起：

| 子图字段 | 内部加载器 / 设置 | 模型目录 |
| --- | --- | --- |
| `unet_name` | Load Diffusion Model（`UNETLoader`） | `models/diffusion_models` |
| `clip_name` | Load CLIP（`CLIPLoader`），类型选 `minimax` | `models/text_encoders` |
| `vae_name` | Load VAE：H3 视频 VAE | `models/vae` |
| `vae_name_1` | Load VAE：H3 音频 VAE | `models/vae` |

请选择本机匹配的 H3 权重，示例文件名需按实际安装替换；插件不会下载模型。连接参考图时选择 **Ref2VA** 扩散模型；不连接参考图时使用兼容的 **FL2VA/T2VA** 模型，接入 `first_frame` 后走图生视频路径。参考图作用于整条视频链，首帧只约束开场。使用 Ref2VA 模型时可以同时连接首帧和参考图。

## H3 Ref Prompt Builder：参考提示词编辑器

编辑 Ref2VA 的六个字段，输出 `prompt`（`STRING`）和 `reference_images`（`IMAGE`）。手动使用无需 LLM。

1. 点击 **＋ 添加图片**，或拖入、粘贴图片。图片顺序对应 `<Picture 1>`、`<Picture 2>` 等。
2. 填写下表六个字段。点击缩略图可插入引用；输入 `<Pic` / `<Sub` 后，用方向键选择，Tab / Enter 补全。
3. 检查实时预览，再运行工作流。手动执行只拼接字段标题与原文，不会用 AI 改写。

| 字段 | 填写内容 |
| --- | --- |
| `subject_definitions` — 主体定义 | 定义 `<Subject N>`，明确对应的来源 `<Picture N>`。一个主体可参考多张图；主体编号和图片编号不必相同。 |
| `summary` — 内容概述 | 简短概述；参考生成使用 `[reference generation]`，有首帧或关键帧时使用 `[keyframe completion + reference generation]`。 |
| `retention_analysis` — 参考保留规则 | 需要保留的参考特征，按用途使用 `fully_preserved`、`partially_preserved`、`attribute_transfer` 或 `weak_reference`。 |
| `detailed_description` — 画面与动作时间线 | 风格、构图、动作、运镜、定时对白和局部音效。时间统一按**最终整片视频**填写。 |
| `overall_soundscape` — 整体环境声 | 整片共同的环境底声与听感；仅属于某场景的声音放在对应镜头或时间段。 |
| `non_diegetic_music` — 背景音乐 | 指定背景音乐；不需要时填写 `None`。 |

例如主体定义可写：`<Subject 1> 是 <Picture 1> 中穿深色衬衫的男子。` 开场使用 `[Shot 1]`；六秒切镜使用 `[Shot 2] At 00:06.000, ...`。`0–3 秒：……` 表示镜头内的事件时间段，不等于切镜。提示词中的总时长应与 `total_seconds` 一致。可用 **填入中文示例** 获得可编辑示例，再按自己的图片调整人物与时间。

**图片操作：**拖动卡片或点击箭头排序，正文中的图片引用编号同步更新；**换**用于替换图片并保留编号。删除图片后，原有引用会标为“已删除”，生成前应修正。不同尺寸的图片补边组批，动图只取第一帧。也可以不用 Builder，直接通过 **Load Image → Batch Images → reference_images** 输入参考图，参见[另一种接线示例](docs/images/long-video-connections.png)。

**导入整段提示词：**展开同名区域。**按标题拆分填入**识别上表六个英文字段名，支持 Markdown 标题和冒号，无需 LLM；没有提供的字段保留现有文字。普通描述使用 **AI 转成六段**，由连接的 Prompt API/Local 模型整理。

**AI 整理：**连接 `prompt_api` 后点击按钮，整理当前六个字段。AI 导入和整理只将 Builder 及其依赖排入队列，不启动视频生成。结果会回填；如果等待期间编辑了原文，则保留为待应用结果，点击 **应用 AI 结果** 才替换。**撤销上次操作**可恢复上一步内容。AI 按钮应在主画布中使用。

**AI 识别参考图**默认开启。AI 导入或整理时，按图片顺序发送等比例缩至最长边不超过 1024px、JPEG 质量 85 的副本，需要所连接模型支持识图；纯文字模型请关闭。远端 API 会收到压缩图片，本地模型通过 AutoProcessor 读取。H3 生成使用源图片，组批时按需补边，不使用给 AI 的压缩副本。普通手动运行 Builder 不会发送 AI 请求。

## H3 Prompt API：远端或本地服务配置

输出 `H3_PROMPT_API` 配置，单独执行这个节点不会请求 API。Builder 在点击 AI 按钮时使用它；Long Video 在生成多段视频时使用它。

| 参数 | 默认值 | 用法 |
| --- | --- | --- |
| `api_url` | `https://api.deepseek.com` | Chat Completions 基础地址，服务要求时保留 `/v1`；也可填写完整 `/chat/completions` 地址。本地服务示例：`http://127.0.0.1:11434/v1`。 |
| `model` | `deepseek-flash` | 服务提供的模型 ID；Builder 开启识图时需使用视觉模型。 |
| `api_key` | 空 | 只填写密钥，不加 `Bearer`；无需认证的本地服务可留空。 |
| `json_mode` | `true` | 请求 `response_format=json_object`。服务不支持时关闭，但模型仍需返回有效 JSON，无需工具调用能力。 |
| `max_tokens` | `16384` | 每次请求的输出预算；回复被截断时可在服务允许范围内增加。 |
| `timeout_seconds` | `180` | 请求超时设置。 |
| `variation` | `0` | 修改后，在下一次执行时重新请求提示词适配。 |
| `log_prompts` | `true` | 保存 AI 输入与回复，也控制所连接 Builder 的日志是否可写入。 |

长视频规划先检查明确的时间与对白边界，再按实际分段窗口（含重叠）生成提示词；为避免切断台词，可能重新分配或延长分段。没有明确时间时，完成时间检查后复用原提示词；只有一段时完全跳过规划。规划失败会在采样前报错。代码对官方 DeepSeek 接口的 `deepseek-flash` 请求低强度思考。

密钥旁的眼睛按钮只控制屏幕显示。密钥仍可能被写入工作流、历史或输出元数据，分享这些文件前需清除。

## H3 Prompt Local：本地模型（实验性）

可替代 Prompt API，输出相同的 `prompt_api` 类型。将完整 Transformers 指令模型放在 `ComfyUI/models/LLM/<模型名>/`，包含配置、tokenizer/chat template 和权重；识图还需要 processor 文件。支持 `extra_model_paths.yaml` 中额外的 `LLM` 目录，在 `model_name` 选择模型文件夹。

| 参数 | 默认值 | 用法 |
| --- | --- | --- |
| `device` | `auto` | 使用 ComfyUI 当前设备；`cpu` 不占 GPU，但更慢。 |
| `free_vram_before_load` | `true` | 加载 LLM 前卸载 ComfyUI 模型，需要生成 H3 时再加载回来。 |
| `quantization` | `none` | `nf4` 通过 bitsandbytes 将未量化权重以 4-bit 加载，不修改原始文件。 |
| `dtype` | `auto` | 可选 `bfloat16`、`float16`、`float32`。 |
| `max_tokens` / `timeout_seconds` | `16384` / `600` | 每次生成的输出预算与超时；超时不包含模型加载时间。 |
| `variation` / `log_prompts` | `0` / `true` | 用途同 Prompt API。 |

模型仅在 AI 编辑或多段规划时加载，完成、失败或取消后卸载，再进入 H3 视频生成。只读取本地权重，不自动下载、不加载远程代码，也不需要 API 服务。不支持 GGUF。Transformers 版本需支持所选模型；本地环境曾使用 Qwen3.5 与 Transformers 5.3.0 验证。16GB 显卡加载 9B 模型时，可使用 `nf4`（需 bitsandbytes）并保持 `free_vram_before_load` 开启；实际显存和提示词遵循效果仍取决于模型与输入。

## H3 Long Video (Simple)：自动生成长视频

连接四路模型、提示词和 **Save Video**。节点自动计算段数，利用上一段的视频/音频 latent 续接，裁掉重叠并以 **24 fps** 拼接。这条路径无需手动放置 Save/Load Latent 或 Chain 节点。

| 参数 | 默认值 | 用法 |
| --- | --- | --- |
| `total_seconds` | `30` | 最终总时长，按 24 fps 四舍五入到帧。 |
| `seed` | `0` | 各段使用 `seed + 段索引`，索引从 0 开始；复现时将生成后控制设为固定。 |
| `width` / `height` | `960` / `544` | 输出宽高，向上取整到 32 的倍数，最小 32。 |
| `segment_seconds` | `15` | 每段采样的目标时长，**包含重叠**，不是每段新增内容时长。 |
| `steps` | `20` | 每段采样步数。 |
| `sampler_name` / `scheduler` | `res_multistep` / `simple` | 原生 ComfyUI 采样器与调度器。 |
| `context_length` | `22` | 视频重叠帧数，可选 `5`、`22`、`39`、`56`；续接段输出时会裁掉。 |
| `audio_context_length` | `24` | 音频续接窗口，以视频帧为单位；`0` 跟随视频重叠跨度。 |
| `tiled_decode` | `true` | 使用原生分块视频 VAE 解码，降低解码显存。 |
| `log_prompts` | `true` | 采样前保存实际各段提示词与设置。 |

种子之后的大多数控件属于高级选项。例如截图的 `total_seconds=24`、`segment_seconds=12`，段数由节点计算。H3 帧对齐、重叠和对白保护会影响实际采样时长，最终保留帧数仍以 `total_seconds` 为目标。为避免末尾出现很短的一段，最后一段可在帧对齐前额外延长约一秒。分段越短不一定越快，因为每段都有编码、解码和续接开销。

未连接 `prompt_api` 时，每段复用同一份提示词；连接后，多段规划会将整片时间换算为段内时间。`prompt_preview` 输出实际各段提示词和时间窗口。Long Video 返回临时拼接视频，需连接 **Save Video** 才能保存到输出目录。

## 日志与常见问题

日志位于 `ComfyUI/output/h3_prompt_logs/`，同时提供可读 TXT 和结构化 JSON，通过任务 ID（`prompt_id`）关联队列/历史。

| 文件后缀 | 内容 | 控制开关 |
| --- | --- | --- |
| `*_builder` | 原文字段、最终提示词、AI system/user 输入与回复、图片信息；编辑器显示最近路径 | Builder 的 `log_prompts`，以及已连接 Prompt API/Local 的 `log_prompts` |
| `*_planner` | 时间分析、分段改写的输入与回复，包括失败记录 | Prompt API/Local 的 `log_prompts` |
| `*_video` | 原提示词、实际分段提示词与时间、种子及采样设置，在采样前保存 | Long Video 的 `log_prompts`，独立控制 |

`prepared` 表示准备采样，不代表视频生成成功。Builder 日志描述其输出，下游改写以视频日志为准。只要 Long Video 实际执行，即使 Builder 命中缓存或未连接 LLM，也可保存视频日志；整条链路命中缓存时不会新增日志。日志不写入密钥、图片二进制或独立 reasoning 字段，但会保留提示词正文。

- **更新后没有编辑器或新接口：**重启 ComfyUI 并刷新浏览器，检查是否重复安装。
- **提示缺少原生 Concatenate Video：**更新 ComfyUI 后重启。
- **AI 不支持图片：**换视觉模型或关闭 **AI 识别参考图**；纯文字分段规划不需要识图能力。
- **JSON 无效或回复截断：**检查地址、模型与 `json_mode`，截断时增加 `max_tokens`，或修改 `variation` 重试。
- **本地模型列表为空：**确认完整模型文件夹位于 `models/LLM` 下且包含 `config.json`，再刷新或重启。

## 原有续接节点

原有 **H3 Motion Context**、**Trim**、**Save Latent**、**Load Latent**、**Chain** 和 **Seam Probe** 仍可用于手动续接和诊断。用法见[原项目文档](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context#readme)及[原版工作流](example_workflows/MiniMax%20H3%20-%20fl2va%20-%20ref2va.json)。

[GPL-3.0 许可证](LICENSE)
