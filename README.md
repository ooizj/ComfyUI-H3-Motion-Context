# H3 Motion Context

[简体中文](README_zh-CN.md)

Generate long MiniMax H3 videos with one prompt and a total duration. Based on [NikoDemon80/ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context), with a reference-prompt editor and automatic segment generation.

Install under `ComfyUI/custom_nodes`, restart and refresh the browser. Requires ComfyUI with native H3 and **Concatenate Video** support.

```sh
git clone https://github.com/ooizj/ComfyUI-H3-Motion-Context.git comfyui-h3-motion-context
```

Example workflows:

- [H3 Long Video - Simple](example_workflows/H3%20Long%20Video%20-%20Simple.json): enter the prompt directly and load the first frame and references with image nodes.
- [H3 Long Video - Ref Prompt Builder](example_workflows/H3%20Long%20Video%20-%20Ref%20Prompt%20Builder.json): manage reference pictures and six prompt sections in the editor, then connect it to Long Video.

Select your installed models and images after importing. The examples retain LoRA/attention settings inside their model subgraphs; adjust them to your installation. The Builder example also includes a resolution selector; if unavailable, set Long Video's width and height directly. API keys have been cleared from the published files; enter your own only when using the API.

## H3 Image & Prompt

[![H3 Image & Prompt example](docs/images/image-and-prompt.png)](docs/images/image-and-prompt.png)

Find it under `video/minimax`. Add, drop or paste pictures and enter a prompt in one text field. Replace pictures or reorder them with the arrows; `<Picture N>` references update with the order. Click a thumbnail to insert its reference.

Connect `prompt` and `reference_images` to a generation node. The prompt is passed through unchanged; pictures follow the displayed order and are padded without cropping when their sizes differ. Text-only output is supported.

**backup** saves the original pictures, `prompt.txt` and a manifest with image order, sources and hashes in a new timestamped folder under `ComfyUI/output/h3_prompt_backups` (following ComfyUI's output directory). The node displays the full path. Backups never overwrite earlier saves, and normal queue execution does not create backups.

**load** opens a list of backups, newest first, with thumbnails, image counts and prompt excerpts. Select one to preview all pictures and the full prompt, then click **载入所选备份** to replace the node contents. Cancel leaves the current contents unchanged. Loaded pictures come from the backup copies, so the original uploads are not required.

## H3 Ref Prompt Builder

[![H3 Ref Prompt Builder example](docs/images/ref-prompt-builder.png)](docs/images/ref-prompt-builder.png)

Find it under `video/minimax`. It manages reference pictures and six Ref2VA prompt sections. Manual editing needs no API.

1. Add, drop or paste pictures, ordered as `<Picture 1>`, `<Picture 2>`, etc. Drag cards or use arrows to reorder; picture references in the text update together. **换** replaces a picture while keeping its number.
2. Fill the six fields. Click a thumbnail to insert a reference, or type `<Pic` / `<Sub` and complete with arrow keys and Tab/Enter. `<Subject N>` identifies a subject: explicitly bind its source pictures rather than assuming subject and picture numbers match.
3. Connect `prompt` and `reference_images` to the matching Long Video inputs, inspect the preview and run. Convert Long Video's `prompt` text widget to an input if needed.

| Field | Content |
| --- | --- |
| `subject_definitions` | Subject features and image sources, e.g. `<Subject 1> is the man wearing a dark shirt in <Picture 1>.` |
| `summary` | Main events, prefixed with `[reference generation]`, or `[keyframe completion + reference generation]` when using a first frame/keyframe. |
| `retention_analysis` | Identity, clothing, environment and other reference features to preserve. |
| `detailed_description` | Composition, actions, camera, dialogue and local sound effects, timed against the whole final video. |
| `overall_soundscape` | Shared ambience and overall sound balance. |
| `non_diegetic_music` | Music instructions, or `None` for no music. |

Use `[Shot 1]` for the opening and `[Shot 2] At 00:06.000, ...` for a cut at six seconds. An event range such as `0–3 seconds: ...` is not a cut. Keep the prompt's total duration consistent with Long Video's `total_seconds`.

**Import a full prompt:** expand **导入整段提示词**. **按标题拆分填入** splits the six English field headings above, with Markdown headings or colons supported, without an API. Use **AI 转成六段** for free-form text, or **填入中文示例** for an editable Chinese example.

**AI editing:** connect H3 Prompt API to Builder's `prompt_api`. Only clicking **AI 整理** or **AI 转成六段** requests the API; this queues prompt processing without starting video generation. Results refill the fields and can be edited or undone. If you changed the original while waiting, click **应用 AI 结果** to apply the pending result. Normal execution, manual editing and heading-based imports make no API calls.

**AI 识别参考图:** enabled by default. Sends pictures in order as compressed JPEG copies with a maximum 1024 px long edge to a vision model. Turn it off for text-only models. Video generation uses the source pictures, padded for batching when sizes differ.

## H3 Long Video (Simple)

[![H3 Long Video (Simple) example](docs/images/long-video-connections.png)](docs/images/long-video-connections.png)

Connect the four model inputs, enter the full prompt and total duration, and connect `VIDEO` to **Save Video**. The node calculates segment count, samples, continues from the previous video/audio latent, trims overlap and joins at **24 fps**.

- `first_frame`: optional opening image, used only in the first segment.
- `reference_images`: optional pictures in `<Picture N>` order, used across all segments. Connect Builder or combine images with Batch Images. Use a Ref2VA model with references, or a compatible FL2VA/T2VA model without them.
- `prompt_api`: optional automatic prompt splitting. Leave disconnected when prompt splitting is not needed.
- `prompt_preview`: actual segment prompts and timing windows; connect a text-display node to inspect it.

| Parameter | Default | Purpose |
| --- | --- | --- |
| `total_seconds` | `30` | Final video duration. |
| `segment_seconds` | `15` | Target sampled duration per segment, including overlap; frame alignment and dialogue protection affect actual lengths. |
| `width` / `height` | `960` / `544` | Output size, rounded up to multiples of 32. |
| `seed` | `0` | Segment seeds are `seed + segment index`, starting at 0. |
| `steps` | `20` | Sampling steps per segment. |
| `sampler_name` / `scheduler` | `res_multistep` / `simple` | Sampler and schedule. |
| `context_length` | `22` | Video overlap in frames: `5`, `22`, `39` or `56`. |
| `audio_context_length` | `24` | Audio continuation window in video-frame units; `0` follows the video overlap. |
| `tiled_decode` | `true` | Tiled decoding to reduce decoding memory. |

The screenshot uses `total_seconds=14` and `segment_seconds=7` to generate an approximately 14-second video in segments. No manual segment count is needed. Shorter segments generally reduce memory per sampling pass, but add encoding, decoding and continuation overhead, so they are not necessarily faster.

### Why split the prompt?

Each short segment is sampled separately with its own time starting at zero. Giving every segment the whole story can repeat opening actions/dialogue or confuse whole-video times with the current segment's times.

With `prompt_api` connected, the node analyzes the timeline and dialogue, then adapts the full prompt to each segment's content. It converts whole-video times to segment-local times, accounts for overlap, and can adjust boundaries to avoid cutting a spoken line. Write explicit whole-video time ranges and dialogue in your source prompt.

**If prompt splitting is not needed, disconnect Long Video's `prompt_api`: video generation still runs in segments, each reuses the original prompt, and no prompt API is called during video generation.**

| Situation | Does Long Video call the API? |
| --- | --- |
| `prompt_api` disconnected | No; the prompt is not split. |
| Only one segment is actually needed, even with `prompt_api` connected | No; uses the original prompt directly. |
| `prompt_api` connected and multiple segments needed | Yes; analyzes timing, then rewrites segment prompts as needed. Without explicit times, it reuses the original after analysis. |

Builder's AI buttons are independent and still call their connected API when clicked. Omitting timestamps does not disable API calls; disconnect Long Video's `prompt_api` to skip automatic prompt splitting.

With `log_prompts` enabled, logs go to `output/h3_prompt_logs/` (TXT + JSON): `*_builder` records editor input/output, `*_planner` records API planning, and `*_video` records final segment prompts/settings before sampling. Builder logging also requires its connected API's `log_prompts` to be enabled. `prepared` means ready for sampling only. The key mask hides its display, not its saved value; clear actual key fields before sharing workflows.

[GPL-3.0 license](LICENSE)
