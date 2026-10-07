"""Generate and join an H3 chain in one execution."""

from fractions import Fraction
import logging
import math
import os
import tempfile
import time
import uuid

import comfy.model_management
import comfy.samplers
import comfy.utils
import folder_paths
import node_helpers
import nodes
from comfy_api.latest import InputImpl, Types, io
from comfy_execution.utils import get_executing_context
from comfy_extras.nodes_audio import VAEDecodeAudio
from comfy_extras.nodes_custom_sampler import (
    BasicGuider, BasicScheduler, KSamplerSelect, RandomNoise, SamplerCustomAdvanced,
)
from comfy_extras.nodes_minimax_h3 import (
    EmptyMiniMaxH3LatentAV, MiniMaxH3AddGuide, MiniMaxH3ImageToVideo,
    MiniMaxH3ReferenceToVideo, align_frame_count,
)

from .nodes import FPS, MiniMaxH3MotionContext, MiniMaxH3MotionContextTrim
from .prompt_planner import prompt_preview, segment_schedule, split_prompts
from .prompt_log import new_prompt_log_path, write_prompt_log

_LOG = logging.getLogger("h3_motion_context")


class _LongVideoProgress:
    def __init__(self, total):
        self.bar = comfy.utils.ProgressBar(total)
        self.original_hook = self.bar.hook
        self.context = get_executing_context()
        self.hook = self.update
        self.active = False
        self.completed = 0
        self.units = 0
        self.track = False

    def __enter__(self):
        self.bar.update_absolute(0)
        self.active = self.original_hook is not None and self.context is not None
        if self.active:
            comfy.utils.set_progress_bar_global_hook(self.hook)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.active = False
        if comfy.utils.PROGRESS_BAR_HOOK is self.hook:
            comfy.utils.set_progress_bar_global_hook(self.original_hook)

    def begin(self, units, track=False):
        self.units = units
        self.track = track

    def finish(self):
        self.completed += self.units
        self.units = 0
        self.track = False
        self.bar.update_absolute(self.completed)

    def update(self, value, total, preview, prompt_id=None, node_id=None):
        # Native samplers and VAEs report their own 0-100% to the same node.
        if (self.active and get_executing_context() == self.context
                and prompt_id in (None, self.context.prompt_id)
                and node_id in (None, self.context.node_id)):
            fraction = min(1.0, max(0.0, value / total)) if self.track and total > 0 else 0.0
            current = max(self.bar.current, self.completed + self.units * fraction)
            self.bar.update_absolute(current, preview=preview)
        else:
            kwargs = {"node_id": node_id}
            if prompt_id is not None:
                kwargs["prompt_id"] = prompt_id
            self.original_hook(value, total, preview, **kwargs)


def plan_segments(total_seconds, segment_seconds, context_length):
    if not math.isfinite(total_seconds) or total_seconds <= 0:
        raise ValueError("Total duration must be a positive number of seconds.")
    if not math.isfinite(segment_seconds) or segment_seconds <= 0:
        raise ValueError("Segment duration must be a positive number of seconds.")
    remaining = max(1, round(total_seconds * FPS))
    clip_frames = align_frame_count(max(5, round(segment_seconds * FPS), context_length + 1))
    tail_limit = align_frame_count(clip_frames + FPS)
    plan = []
    while remaining:
        overlap = context_length if plan else 0
        tail_frames = align_frame_count(max(5, remaining + overlap))
        # Allow one extra second, aligned to H3's grid, to avoid a tiny last clip.
        length = tail_frames if tail_frames <= tail_limit else clip_frames
        keep = min(remaining, length - overlap)
        plan.append((length, overlap, keep))
        remaining -= keep
    return plan


class MiniMaxH3LongVideo(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3LongVideo",
            display_name="H3 Long Video (Simple)",
            category="video/minimax",
            description="Generate short H3 clips, continue their motion and audio, and return one video. Connect VIDEO to Save Video. Requires ComfyUI's native Concatenate Video support. Use an FL2VA/T2VA model without references, or a Ref2VA model with reference images.",
            inputs=[
                io.Model.Input("model"),
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("prompt", default="", multiline=True, dynamic_prompts=True, optional=True,
                    tooltip="Write one complete H3 prompt for the entire video, with final-video timestamps if wanted. Connect prompt_api to adapt it automatically to sampled segments; without it, the same prompt is reused."),
                io.Float.Input("total_seconds", default=30.0, min=0.1, max=86400.0, step=0.1, optional=True,
                    tooltip="Final duration at 24 fps. Segment count is calculated automatically from segment_seconds and context_length."),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff, control_after_generate=True, optional=True),
                io.Int.Input("width", default=960, min=32, max=nodes.MAX_RESOLUTION, step=32, advanced=True, optional=True),
                io.Int.Input("height", default=544, min=32, max=nodes.MAX_RESOLUTION, step=32, advanced=True, optional=True),
                io.Float.Input("segment_seconds", default=15.0, min=0.1, max=150.0, step=0.1, advanced=True, optional=True,
                    tooltip="Target duration sampled per segment, INCLUDING overlap. Use 15 seconds when memory allows; shorter segments add encoding, decoding and continuation overhead. Prompt API may rebalance or lengthen clips to keep timed speech intact. The last segment may extend by about one second, rounded up to H3's frame grid."),
                io.Int.Input("steps", default=20, min=1, max=10000, advanced=True, optional=True),
                io.Combo.Input("sampler_name", options=comfy.samplers.SAMPLER_NAMES, default="res_multistep", advanced=True, optional=True),
                io.Combo.Input("scheduler", options=comfy.samplers.SCHEDULER_NAMES, default="simple", advanced=True, optional=True),
                io.Combo.Input("context_length", options=["22", "5", "39", "56"], default="22", advanced=True, optional=True),
                io.Int.Input("audio_context_length", default=24, min=0, max=240, advanced=True, optional=True),
                io.Boolean.Input("tiled_decode", default=True, advanced=True, optional=True,
                    tooltip="Use the stock tiled video VAE decoder to reduce decoding memory."),
                io.Image.Input("first_frame", optional=True,
                    tooltip="Optional opening image, used only for the first segment."),
                io.Image.Input("reference_images", optional=True,
                    tooltip="Optional image batch for a Ref2VA model. Every image is a reference: <Picture 1>, <Picture 2>, etc. Use Image Batch to combine images. References stay attached throughout the chain."),
                io.Custom("H3_PROMPT_API").Input("prompt_api", optional=True,
                    tooltip="Connect H3 Prompt API for automatic segment prompts. Leave disconnected to reuse the original prompt without API calls. A single-segment video also skips the API."),
                io.Boolean.Input("log_prompts", default=True, optional=True, advanced=True,
                    tooltip="Save the input and final per-segment prompts, seeds and task ID to output/h3_prompt_logs before sampling, including when Prompt Builder is cached. Prompt API log_prompts controls AI planning logs separately."),
            ],
            outputs=[io.Video.Output(), io.String.Output(display_name="prompt_preview")],
        )

    @classmethod
    def execute(cls, model, clip, vae, audio_vae, prompt="", total_seconds=30.0, seed=0,
                width=960, height=544, segment_seconds=15.0, steps=20,
                sampler_name="res_multistep", scheduler="simple", context_length="22",
                audio_context_length=24, tiled_decode=True, first_frame=None,
                reference_images=None, prompt_api=None, log_prompts=True):
        if not hasattr(InputImpl, "VideoFromList"):
            raise RuntimeError("H3 Long Video needs native Concatenate Video support. Update ComfyUI to use this node.")
        plan = plan_segments(total_seconds, segment_seconds, int(context_length))
        schedule = segment_schedule(plan)
        prompts = [prompt] * len(plan)
        reference_count = len(reference_images) if reference_images is not None else 0
        if prompt_api is not None and len(plan) > 1:
            input_mode = "Ref2VA" if reference_count else "I2VA" if first_frame is not None else "T2VA"
            schedule, prompts = split_prompts(prompt, schedule, input_mode, reference_count, **prompt_api)
            plan = [(s["sampled_frames"], s["overlap_frames"], s["retained_frames"]) for s in schedule]
        _LOG.info("H3 Long Video: %.3fs output, %d segment(s), %.3fs sampled before trimming",
                  sum(keep for _, _, keep in plan) / FPS, len(plan), sum(length for length, _, _ in plan) / FPS)
        preview = prompt_preview(schedule, prompts)
        width = max(32, math.ceil(width / 32) * 32)
        height = max(32, math.ceil(height / 32) * 32)
        if log_prompts:
            report = {
                "operation": "video_generation", "status": "prepared",
                "original_prompt": prompt, "prompts": prompts, "schedule": schedule,
                "seeds": [(seed + i) % (1 << 64) for i in range(len(plan))],
                "width": width, "height": height, "steps": steps,
                "sampler_name": sampler_name, "scheduler": scheduler,
                "reference_image_count": reference_count, "has_first_frame": first_frame is not None,
            }
            text = (f"Seeds: {report['seeds']}\nSize: {width}x{height}\nSteps: {steps}\n"
                    f"Sampler: {sampler_name}\nScheduler: {scheduler}\n\nOriginal prompt:\n\n{prompt}\n\n"
                    f"Final sampling prompts (prepared before sampling):\n\n{preview}")
            write_prompt_log(new_prompt_log_path("video"), report, text, (prompt_api or {}).get("api_key", ""))
        sampler, = KSamplerSelect.execute(sampler_name).result
        sigmas, = BasicScheduler.execute(model, scheduler, steps, 1.0).result
        references = {f"ref_image_{i}": img.unsqueeze(0) for i, img in enumerate(reference_images)} if reference_images is not None else {}
        context = MiniMaxH3MotionContext()
        trim = MiniMaxH3MotionContextTrim()
        sampling_steps = max(0, sigmas.shape[-1] - 1)
        previous = None
        conditioning = None
        reference_latents = None
        temp_root = folder_paths.get_temp_directory()
        os.makedirs(temp_root, exist_ok=True)
        final_path = os.path.join(temp_root, f"h3_long_{uuid.uuid4().hex}.mp4")

        with tempfile.TemporaryDirectory(prefix="h3_segments_", dir=temp_root) as segment_dir, \
                _LongVideoProgress(len(plan) * (sampling_steps + 3) + 1) as progress:
            videos = []
            # Group model work without retaining a whole film's conditioning or latents.
            for batch_start in range(0, len(plan), 3):
                batch_end = min(batch_start + 3, len(plan))
                _LOG.info("H3 Long Video: preparing prompts %d-%d/%d", batch_start + 1, batch_end, len(plan))
                prepared = []
                for index in range(batch_start, batch_end):
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    progress.begin(1)
                    encoding_started = time.perf_counter()
                    length = plan[index][0]
                    prompt = prompts[index]
                    if (conditioning is None or prompt != prompts[index - 1]
                            or (index == 1 and first_frame is not None and not references)):
                        if references:
                            conditioning, latent = MiniMaxH3ReferenceToVideo.execute(
                                clip=clip, vae=vae if reference_latents is None else None,
                                audio_vae=audio_vae, prompt=prompt,
                                width=width, height=height, length=length,
                                ref_images=references).result
                            if reference_latents is None:
                                reference_latents = conditioning[0][1]["minimax_refs"]
                            else:
                                conditioning = node_helpers.conditioning_set_values(
                                    conditioning, {"minimax_refs": reference_latents})
                        else:
                            conditioning, latent = MiniMaxH3ImageToVideo.execute(
                                clip=clip, vae=vae, prompt=prompt, width=width, height=height,
                                length=length, first_frame=first_frame if index == 0 else None).result
                    else:
                        latent, = EmptyMiniMaxH3LatentAV.execute(width, height, length).result
                    prepared.append((conditioning, latent, time.perf_counter() - encoding_started))
                    progress.finish()

                sampled_segments = []
                for index in range(batch_start, batch_end):
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    _LOG.info("H3 Long Video: sampling segment %d/%d, %d new frames", index + 1, len(plan), plan[index][2])
                    preparation_started = time.perf_counter()
                    positive, latent, conditioning_seconds = prepared[index - batch_start]
                    prepared[index - batch_start] = None
                    if index == 0 and references and first_frame is not None:
                        positive, = MiniMaxH3AddGuide.execute(
                            positive, latent, frame_idx=0, vae=vae, image=first_frame[:1]).result
                    positive, trim_frames = context.apply(
                        positive, vae, latent, context_length, audio_context_length,
                        context_latent=previous)
                    guider, = BasicGuider.execute(model, positive).result
                    noise, = RandomNoise.execute((seed + index) % (1 << 64)).result
                    sampling_started = time.perf_counter()
                    conditioning_seconds += sampling_started - preparation_started
                    progress.begin(sampling_steps, track=True)
                    sampled, denoised = SamplerCustomAdvanced.execute(noise, guider, sampler, sigmas, latent).result
                    sampling_seconds = time.perf_counter() - sampling_started
                    progress.finish()
                    previous = sampled
                    sampled_segments.append((sampled, trim_frames, conditioning_seconds, sampling_seconds))
                    del denoised, sampled, positive, guider, noise, latent

                for index in range(batch_start, batch_end):
                    comfy.model_management.throw_exception_if_processing_interrupted()
                    _LOG.info("H3 Long Video: decoding segment %d/%d", index + 1, len(plan))
                    progress.begin(1, track=True)
                    decoding_started = time.perf_counter()
                    sampled, trim_frames, conditioning_seconds, sampling_seconds = sampled_segments[index - batch_start]
                    sampled_segments[index - batch_start] = None
                    _, overlap, keep = plan[index]
                    if tiled_decode:
                        images, = nodes.VAEDecodeTiled().decode(vae, sampled, tile_size=512)
                    else:
                        images, = nodes.VAEDecode().decode(vae, sampled)
                    audio, = VAEDecodeAudio.execute(audio_vae, sampled).result
                    del sampled
                    if trim_frames != overlap or images.shape[0] < trim_frames + keep:
                        raise RuntimeError("H3 frame layout changed: decoded frames or context overlap do not match the segment plan.")
                    images, audio = trim.trim(images[:trim_frames + keep], trim_frames, audio, fps=FPS, match_tail=True)
                    progress.finish()
                    progress.begin(1, track=True)
                    saving_started = time.perf_counter()
                    segment = InputImpl.VideoFromComponents(Types.VideoComponents(
                        images=images, audio=audio, frame_rate=Fraction(FPS)))
                    path = os.path.join(segment_dir, f"{index:06d}.mp4")
                    segment.save_to(path, format=Types.VideoContainer.MP4, codec=Types.VideoCodec.H264)
                    videos.append(InputImpl.VideoFromFile(path))
                    del images, audio, segment
                    _LOG.info("H3 Long Video: segment %d wall time: conditioning %.1fs, sampling %.1fs, decoding %.1fs, saving %.1fs",
                              index + 1, conditioning_seconds, sampling_seconds,
                              saving_started - decoding_started, time.perf_counter() - saving_started)
                    progress.finish()

            del previous, conditioning, reference_latents
            comfy.model_management.throw_exception_if_processing_interrupted()
            progress.begin(1)
            joining_started = time.perf_counter()
            InputImpl.VideoFromList(videos).save_to(final_path, format=Types.VideoContainer.MP4)
            _LOG.info("H3 Long Video: final video assembly %.1fs", time.perf_counter() - joining_started)
            progress.finish()
        return io.NodeOutput(InputImpl.VideoFromFile(final_path), preview)


NODE_CLASS_MAPPINGS = {"MiniMaxH3LongVideo": MiniMaxH3LongVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3LongVideo": "H3 Long Video (Simple)"}
