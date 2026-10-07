# H3 Motion Context

[简体中文](README_zh-CN.md)

Generate long MiniMax H3 videos with one prompt and a total duration. This fork of [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context) adds automatic sampling, motion/audio continuation, overlap trimming and joining, plus a reference-prompt editor and optional AI prompt planning. The original chaining nodes remain available.

## Install and open the example

Requires ComfyUI with native H3, arbitrary keyframe anchors (ComfyUI 0.34.0+) and **Concatenate Video** support. Long Video also checks for native video concatenation at runtime.

From `ComfyUI/custom_nodes`, install this fork and restart ComfyUI:

```sh
git clone https://github.com/ooizj/ComfyUI-H3-Motion-Context.git comfyui-h3-motion-context
```

Keep one installation of this pack to avoid duplicate node IDs. If already installed, update that checkout instead of cloning a second copy. Refresh the browser after updating frontend files.

Open [H3 Long Video - Simple.json](example_workflows/H3%20Long%20Video%20-%20Simple.json). This minimal example contains **H3 Model Loader → H3 Long Video (Simple) → Save Video**. Choose installed models, enter `prompt` and `total_seconds`, then run. Add the optional prompt nodes from `video/minimax` for the reference-image workflow below.

## Connect the nodes

[![Reference Prompt Builder, Prompt API and Long Video connections](docs/images/ref-prompt-builder.png)](docs/images/ref-prompt-builder.png)

| From | To | Purpose |
| --- | --- | --- |
| Model Loader: `MODEL`, `CLIP`, `VAE`, `AUDIO_VAE` | Long Video: `model`, `clip`, `vae`, `audio_vae` | H3 generation models |
| Ref Prompt Builder: `prompt` | Long Video: `prompt` | Complete six-section prompt; convert the text widget to an input if needed |
| Ref Prompt Builder: `reference_images` | Long Video: `reference_images` | Pictures in the same order as `<Picture N>` |
| Prompt API **or** Prompt Local: `prompt_api` | Builder: `prompt_api` | Optional AI editing/import |
| The same Prompt API/Local output | Long Video: `prompt_api` | Optional prompt planning for multiple segments |
| Load Image: `IMAGE` | Long Video: `first_frame` | Optional opening composition, used only in segment 1 |
| Long Video: `VIDEO` | Save Video: `video` | Save the assembled video with audio |
| Long Video: `prompt_preview` | An optional text-display node | Inspect segment prompts and timing after execution |

The two `prompt_api` connections serve different operations. Connect both to use both AI editing and segment planning; either can be omitted. The H3 `clip` text encoder is separate from the optional prompt-planning LLM.

The screenshot's **resolution selector** is an optional external node, not part of this pack. Connect its integer outputs to `width` and `height`, or set those values directly in Long Video's advanced inputs. Screenshot values are examples, not node defaults.

### H3 Model Loader

**H3 Model Loader is a subgraph in the example workflow**, not another registered node. It groups standard ComfyUI loaders:

| Subgraph field | Standard loader / setting | Model location |
| --- | --- | --- |
| `unet_name` | Load Diffusion Model (`UNETLoader`) | `models/diffusion_models` |
| `clip_name` | Load CLIP (`CLIPLoader`), type `minimax` | `models/text_encoders` |
| `vae_name` | Load VAE: H3 video VAE | `models/vae` |
| `vae_name_1` | Load VAE: H3 audio VAE | `models/vae` |

Select matching installed H3 weights; replace example filenames with your local choices. The pack does not download models. With reference pictures, select a **Ref2VA** diffusion model. Without references, use a compatible **FL2VA/T2VA** model; connecting `first_frame` selects the image-to-video path. References remain attached to every segment, while `first_frame` only anchors the opening. Both image inputs can be connected together with a Ref2VA model.

## H3 Ref Prompt Builder

Edits six Ref2VA sections and outputs `prompt` (`STRING`) and `reference_images` (`IMAGE`). Manual use needs no LLM.

1. Click **＋ 添加图片**, drop files or paste images. Cards become `<Picture 1>`, `<Picture 2>`, etc. in order.
2. Fill the fields below. Click a thumbnail to insert its reference, or type `<Pic` / `<Sub` and use arrow keys plus Tab/Enter to complete it.
3. Inspect the live preview, then run. Manual execution joins the section headings and your text without AI rewriting.

| Field | What to enter |
| --- | --- |
| `subject_definitions` — 主体定义 | Define each `<Subject N>` and explicitly bind its source `<Picture N>`. One subject may use several pictures; subject and picture numbers need not match. |
| `summary` — 内容概述 | A short overview with `[reference generation]`, or `[keyframe completion + reference generation]` when using a first frame/keyframe. |
| `retention_analysis` — 参考保留规则 | Reference features to preserve. Use `fully_preserved`, `partially_preserved`, `attribute_transfer` or `weak_reference` as appropriate. |
| `detailed_description` — 画面与动作时间线 | Style, composition, actions, camera, timed dialogue and local sound effects. Write times against the **whole final video**. |
| `overall_soundscape` — 整体环境声 | Shared ambience and overall sound balance; place location-specific sounds in their own scene/time range. |
| `non_diegetic_music` — 背景音乐 | Requested background music, or `None` for none. |

A subject definition can be `<Subject 1> is the man wearing a dark shirt in <Picture 1>.` Use `[Shot 1]` for the opening and `[Shot 2] At 00:06.000, ...` for a cut at six seconds. Event ranges such as `0–3 seconds: ...` describe actions within a shot; they do not imply a cut. Keep the prompt's duration consistent with `total_seconds`. **填入中文示例** supplies an editable example; adapt its identities and timings to your pictures.

**Pictures:** drag cards or use arrows to reorder; picture references in the fields are renumbered together. **换** replaces a picture while keeping its number. Removing a picture marks its references as deleted; correct those before generating. Different sizes are padded for batching; animated files use the first frame. You can skip Builder and use **Load Image → Batch Images → reference_images**, as in the [alternative connection example](docs/images/long-video-connections.png).

**Import:** expand **导入整段提示词**. **按标题拆分填入** recognizes the six English field names above, optionally with Markdown headings or colons, without an LLM. Missing sections keep existing text. **AI 转成六段** converts free-form text with the connected Prompt API/Local model.

**AI editing:** connect `prompt_api` and click **AI 整理** to revise current fields. AI import/edit queues only Builder and its dependencies, without starting video generation. Results refill the editor; if you edit while waiting, they stay pending until **应用 AI 结果**. **撤销上次操作** restores the previous state. Use the AI buttons on the main canvas.

**AI 识别参考图** is on by default. AI import/edit sends copies resized proportionally to at most 1024 px on the long edge, as JPEG quality 85, in picture order. The model must support images; turn this off for text-only models. Remote APIs receive these compressed images; local models use AutoProcessor. H3 uses the source pictures, with padding when batching, rather than the compressed AI copies. Running Builder manually does not send an AI request.

## H3 Prompt API

Outputs an `H3_PROMPT_API` configuration. This node alone makes no request. Builder uses it when you click an AI button; Long Video uses it for multiple segments.

| Parameter | Default | Usage |
| --- | --- | --- |
| `api_url` | `https://api.deepseek.com` | Chat Completions base URL, including `/v1` if required, or the full `/chat/completions` endpoint. Local-server example: `http://127.0.0.1:11434/v1`. |
| `model` | `deepseek-flash` | Model ID served by that endpoint. Use a vision model for Builder image recognition. |
| `api_key` | Empty | Key without `Bearer`; leave empty for an unauthenticated local server. |
| `json_mode` | `true` | Requests `response_format=json_object`. Turn off if unsupported; valid JSON is still required. No tool calling needed. |
| `max_tokens` | `16384` | Output budget per request. Increase for truncated responses within provider limits. |
| `timeout_seconds` | `180` | Request timeout setting. |
| `variation` | `0` | Change to request a new prompt adaptation on the next execution. |
| `log_prompts` | `true` | Save AI requests/replies; also gates a connected Builder's logs. |

For long videos, the planner checks explicit times and speech boundaries, then writes prompts for actual segment windows, including overlap. It may rebalance or lengthen segments to avoid cutting dialogue. Without explicit times, it reuses the original prompt after the timing check. A single-segment video skips planning entirely. Planning errors stop generation before sampling. The code requests low reasoning effort for `deepseek-flash` on the official DeepSeek endpoint.

The eye button only hides the key on screen. Keys may still be serialized into workflows, history or output metadata; remove them before sharing those files.

## H3 Prompt Local (experimental)

An alternative to Prompt API with the same `prompt_api` output. Put a complete Transformers instruction-model folder under `ComfyUI/models/LLM/<model-name>/`, including config, tokenizer/chat template and weights. Vision use also needs processor files. Additional `LLM` roots in `extra_model_paths.yaml` are supported. Select the folder in `model_name`.

| Parameter | Default | Usage |
| --- | --- | --- |
| `device` | `auto` | ComfyUI's current device; `cpu` avoids GPU use but is slower. |
| `free_vram_before_load` | `true` | Offloads ComfyUI models before loading the LLM. They reload when needed for H3. |
| `quantization` | `none` | `nf4` loads unquantized weights in 4-bit with bitsandbytes, without changing the files. |
| `dtype` | `auto` | Optional dtype: `bfloat16`, `float16` or `float32`. |
| `max_tokens` / `timeout_seconds` | `16384` / `600` | Per-generation output budget and timeout; loading time is excluded. |
| `variation` / `log_prompts` | `0` / `true` | Same purpose as Prompt API. |

The LLM loads for AI editing or multi-segment planning and unloads afterward, including on failure/cancellation, before H3 generation. It reads local weights only: no automatic downloads, remote-code loading or required API server. GGUF is not supported. Use a Transformers version supporting your model; the local setup was tested with Qwen3.5 and Transformers 5.3.0. For a 9B model on a 16GB GPU, use `nf4` with bitsandbytes and keep `free_vram_before_load` enabled. Actual memory use and prompt adherence depend on the model and input.

## H3 Long Video (Simple)

Connect the four model inputs, a prompt and **Save Video**. The node calculates segment count, samples continuations from the previous video/audio latent, removes overlap and joins at **24 fps**. No manual Save/Load Latent or Chain nodes are needed for this path.

| Parameter | Default | Usage |
| --- | --- | --- |
| `total_seconds` | `30` | Final duration, rounded to the nearest frame at 24 fps. |
| `seed` | `0` | Segment seeds are `seed + segment index` (starting at 0). Use fixed seed control to repeat a run. |
| `width` / `height` | `960` / `544` | Output size, rounded up to multiples of 32, minimum 32. |
| `segment_seconds` | `15` | Target sampled duration **including overlap**, not new content per segment. |
| `steps` | `20` | Sampling steps per segment. |
| `sampler_name` / `scheduler` | `res_multistep` / `simple` | Native ComfyUI sampler and schedule. |
| `context_length` | `22` | Video overlap in frames: `5`, `22`, `39`, `56`. Trimmed from each continuation. |
| `audio_context_length` | `24` | Audio continuation window in video-frame units; `0` uses the video overlap span. |
| `tiled_decode` | `true` | Native tiled video VAE decoding to reduce decoding memory. |
| `log_prompts` | `true` | Saves actual planned sampling prompts/settings before sampling. |

Most controls after seed are advanced inputs. With `total_seconds=24` and `segment_seconds=12`, the node calculates the segments itself. H3 frame alignment, overlap and dialogue protection can change sampled durations; final retained frames still target `total_seconds`. The final segment may extend by about a second before frame alignment to avoid a tiny extra segment. Shorter segments are not necessarily faster because each adds encoding, decoding and continuation overhead.

Without `prompt_api`, all segments reuse the prompt. With it, multi-segment planning converts whole-video timestamps to segment-local timing. `prompt_preview` describes the final prompts and windows. Long Video returns a temporary assembled `VIDEO`; connect **Save Video** to keep a file in the output directory.

## Logs and troubleshooting

Logs go to `ComfyUI/output/h3_prompt_logs/`, with readable TXT and structured JSON sharing a task ID (`prompt_id`) for queue/history lookup.

| File suffix | Contents | Switch |
| --- | --- | --- |
| `*_builder` | Input fields, final prompt, AI system/user messages/replies, image metadata; the editor shows the latest path | Builder `log_prompts` and, when connected, Prompt API/Local `log_prompts` |
| `*_planner` | Timing analysis and segment-rewrite requests/replies, including failures | Prompt API/Local `log_prompts` |
| `*_video` | Original prompt, actual segment prompts/timing, seeds and sampling settings, before sampling | Long Video `log_prompts`, independently |

`prepared` means ready to sample, not completed generation. Builder logs describe its output; use video logs for downstream adaptations. Video logs are written even if Builder is cached or no LLM is connected, provided Long Video executes. A fully cached run creates no new logs. Credentials, image bytes and separate reasoning fields are omitted; prompt text is retained.

- **No editor/new inputs after updating:** restart ComfyUI and refresh the browser; check duplicate installations.
- **Missing native Concatenate Video:** update ComfyUI and restart.
- **AI rejects images:** select a vision model or turn off **AI 识别参考图**. Text-only segment planning needs no vision.
- **Invalid/truncated JSON:** check endpoint/model and `json_mode`, increase `max_tokens` for truncation, or change `variation` and retry.
- **No local model listed:** check for `config.json` in a complete model folder under `models/LLM`, then refresh/restart.

## Original chaining nodes

**H3 Motion Context**, **Trim**, **Save Latent**, **Load Latent**, **Chain** and **Seam Probe** remain available for manual chaining and diagnostics. See [original usage documentation](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context#readme) and the [original workflow](example_workflows/MiniMax%20H3%20-%20fl2va%20-%20ref2va.json).

[GPL-3.0 license](LICENSE)
