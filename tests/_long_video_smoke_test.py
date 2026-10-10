"""CPU smoke test with fake inference and real H3 conditioning/video encoding.

Run with ComfyUI's Python from this repository. No model weights are loaded.
For a checkout outside custom_nodes, set COMFYUI_ROOT to the ComfyUI directory.
"""

import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PACKAGE = Path(__file__).resolve().parents[1]
COMFY_ROOT = Path(os.environ.get("COMFYUI_ROOT", PACKAGE.parent.parent))
sys.path.insert(0, str(COMFY_ROOT))
sys.path.insert(0, str(PACKAGE.parent))
sys.argv = [sys.argv[0], "--cpu"]

import comfy.options
comfy.options.enable_args_parsing()
import torch
import folder_paths
from comfy_api.latest import io
from comfy_execution.utils import CurrentNodeContext
from comfy_extras.nodes_minimax_h3 import video_latent_t

long = importlib.import_module(PACKAGE.name + ".long_video")
motion = importlib.import_module(PACKAGE.name + ".nodes")
planner = importlib.import_module(PACKAGE.name + ".prompt_planner")
timing = importlib.import_module(PACKAGE.name + ".prompt_timing")


def test_progress_scope():
    updates = []
    def hook(value, total, preview, **kwargs):
        updates.append((value, total, preview))

    with patch.object(long.comfy.utils, "PROGRESS_BAR_HOOK", hook), CurrentNodeContext("smoke", "long"):
        try:
            with long._LongVideoProgress(10) as progress:
                progress.begin(6, track=True)
                inner = long.comfy.utils.ProgressBar(2)
                inner.update_absolute(1, preview="preview")
                assert updates[-1] == (3, 10, "preview")
                inner.update_absolute(2, preview="preview")
                assert updates[-1] == (6, 10, "preview")
                # A second internal bar must not move the overall bar backwards.
                long.comfy.utils.ProgressBar(4).update_absolute(1, preview="preview")
                assert updates[-1] == (6, 10, "preview")
                with CurrentNodeContext("smoke", "other"):
                    long.comfy.utils.ProgressBar(2).update_absolute(1)
                    assert updates[-1] == (1, 2, None)
                raise RuntimeError("cancelled")
        except RuntimeError as error:
            assert str(error) == "cancelled"
        else:
            raise AssertionError("Progress scope must propagate cancellation")
        assert long.comfy.utils.PROGRESS_BAR_HOOK is hook
        inner.update_absolute(1, preview="preview")
        assert updates[-1] == (1, 2, "preview")

    def cancelled_hook(*args, **kwargs):
        raise RuntimeError("cancelled before start")
    with patch.object(long.comfy.utils, "PROGRESS_BAR_HOOK", cancelled_hook), CurrentNodeContext("smoke", "long"):
        try:
            with long._LongVideoProgress(10):
                raise AssertionError("Cancelled progress must not start")
        except RuntimeError as error:
            assert str(error) == "cancelled before start"
        assert long.comfy.utils.PROGRESS_BAR_HOOK is cancelled_hook


class Clip:
    def __init__(self, events=None):
        self.calls = []
        self.texts = []
        self.events = events

    def tokenize(self, text, **kwargs):
        self.calls.append(kwargs)
        self.texts.append(text)
        return text

    def encode_from_tokens_scheduled(self, tokens):
        if self.events is not None:
            self.events.append(("encode", tokens))
        return [[torch.zeros(1, 1, 8), {}]]


class VideoVAE:
    def __init__(self, events=None):
        self.encode_calls = 0
        self.events = events

    def encode(self, images):
        self.encode_calls += 1
        t = 1 if len(images) == 1 else video_latent_t(len(images))
        return torch.zeros(1, 24, t, images.shape[1] // 16, images.shape[2] // 16)

    def decode(self, z):
        pbar = long.comfy.utils.ProgressBar(2)
        pbar.update_absolute(1, preview="decode-preview")
        pbar.update_absolute(2, preview="decode-preview")
        if self.events is not None:
            self.events.append(("decode", int(z[0, 0, 0, 0, 0])))
        frames = motion._pixel_frames(z.shape[2])
        return torch.full((frames, z.shape[3] * 16, z.shape[4] * 16, 3), float(z[0, 0, 0, 0, 0]) / 10)

    def temporal_compression_decode(self):
        return 3.4

    def spacial_compression_decode(self):
        return 16

    def decode_tiled(self, z, **kwargs):
        return self.decode(z)


class AudioVAE:
    audio_sample_rate = 32000

    def decode(self, z):
        return torch.full((1, z.shape[-1] * 800, 2), 0.05)


def test_prompt_api():
    info = planner.MiniMaxH3PromptAPI.GET_NODE_INFO_V1()
    assert tuple(info["output"]) == ("H3_PROMPT_API",)
    fields = info["input"]["required"] | info["input"]["optional"]
    assert {"api_url", "api_key", "model", "json_mode"} <= fields.keys()
    assert not {"story", "prompt", "total_seconds", "segment_count", "input_mode"} & fields.keys()
    assert fields["api_key"][1]["default"] == ""
    assert fields["log_prompts"][1]["default"] is True
    assert fields["max_tokens"][1]["default"] == 65535
    for base, endpoint in [
        ("https://api.deepseek.com", "https://api.deepseek.com/chat/completions"),
        ("http://127.0.0.1:11434/v1/", "http://127.0.0.1:11434/v1/chat/completions"),
        ("http://localhost:1234/v1/chat/completions", "http://localhost:1234/v1/chat/completions"),
        ("https://example.test/proxy/v1?version=1", "https://example.test/proxy/v1/chat/completions?version=1"),
    ]:
        assert planner.chat_endpoint(base) == endpoint
    schedule = planner.segment_schedule(long.plan_segments(14, 7.5, 22))
    assert schedule[0]["pinned_global_interval"] is None
    assert schedule[1]["pinned_global_interval"] == [8 - 22 / 24, 8]
    full_prompt = "From 0-3s the man says <d>[Chinese] 你好！</d>. From 11-14s they toast."
    speech = [{"text": "<d>[Chinese] 你好！</d>", "start_seconds": 0, "end_seconds": 3}]
    timeline = {"speech": speech}
    expected = ["From 0 to 3 seconds, the man says <d>[Chinese] 你好！</d>.", "From 3.92 to 6.92 seconds, they toast."]

    def response(content, status=200, finish="stop"):
        result = MagicMock(status_code=status)
        result.__enter__.return_value = result
        result.json.return_value = {"choices": [{"finish_reason": finish, "message": {
            "role": "assistant", "content": content if isinstance(content, str) else json.dumps(content),
            "reasoning_content": "private-reasoning-placeholder",
        }}], "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}
        return result

    with patch.object(planner.requests, "post") as post:
        settings, = planner.MiniMaxH3PromptAPI.execute(api_key="smoke-test-placeholder").result
        post.assert_not_called()
        post.side_effect = [response(timeline), response({"prompts": expected})]
        assert planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings) == (schedule, expected)
        assert post.call_count == 2
        first, second = post.call_args_list
        assert first.args == ("https://api.deepseek.com/chat/completions",)
        assert first.kwargs["allow_redirects"] is False
        assert first.kwargs["headers"] == {"Authorization": "Bearer smoke-test-placeholder"}
        assert first.kwargs["json"]["thinking"] == {"type": "enabled"}
        assert first.kwargs["json"]["reasoning_effort"] == "low"
        for call in (first, second):
            payload = call.kwargs["json"]
            assert "tools" not in payload and "tool_choice" not in payload
            assert payload["response_format"] == {"type": "json_object"}
            assert [m["role"] for m in payload["messages"]] == ["system", "user"]
        request = json.loads(second.kwargs["json"]["messages"][1]["content"])
        assert request["full_h3_prompt"] == full_prompt and request["reference_image_count"] == 3
        assert request["input_mode"] == "Ref2VA" and len(request["clips"]) == 2
        assert request["clips"][0]["speech"][0]["local_seconds"] == [0, 3]
        assert request["clips"][1]["global_time_at_local_zero"] == 7.08
        log_directory = Path(folder_paths.get_output_directory()) / "h3_prompt_logs"
        saved_path, = log_directory.glob("*.json")
        saved_text = saved_path.read_text(encoding="utf-8")
        saved = json.loads(saved_text)
        assert saved["prompts"] == expected and saved["status"] == "ok"
        assert saved["timeline"] == timeline and len(saved["responses"]) == 2
        assert [r["stage"] for r in saved["requests"]] == ["timeline", "prompts"]
        assert saved["requests"][0]["messages"] == first.kwargs["json"]["messages"]
        assert saved["requests"][1]["messages"] == second.kwargs["json"]["messages"]
        assert saved["usage"]["total_tokens"] == 60
        assert "smoke-test-placeholder" not in saved_text and "private-reasoning-placeholder" not in saved_text
        readable = saved_path.with_suffix(".txt").read_text(encoding="utf-8")
        assert "8.000-14.000s" in readable and "Time tool trace" not in readable
        assert planner.TIMELINE_PROMPT in readable and planner.SYSTEM_PROMPT in readable

        local_settings, = planner.MiniMaxH3PromptAPI.execute(api_url="http://localhost:1234/v1/chat/completions",
            model="local-model", json_mode=False, max_tokens=4096, timeout_seconds=60).result
        post.side_effect = [response(timeline), response("```json\n" + json.dumps({"prompts": expected}) + "\n```")]
        prompts = planner.split_prompts(full_prompt, schedule, "I2VA", 0, **local_settings)[1]
        assert prompts[0].startswith("For the target video, at 0.00 seconds")
        assert not prompts[1].startswith("For the target video")
        assert post.call_args.args == ("http://localhost:1234/v1/chat/completions",)
        assert post.call_args.kwargs["headers"] == {} and post.call_args.kwargs["timeout"] == (10, 60)
        assert "response_format" not in post.call_args.kwargs["json"]
        assert "thinking" not in post.call_args.kwargs["json"]
        post.side_effect = [response(timeline), response({"prompts": [expected[0].replace("the man", "<Subject 1>（S1）"), expected[1]]})]
        prompts = planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings)[1]
        assert prompts[0].startswith("From 0 to 3 seconds, <Subject 1>(S1) says") and "（" not in prompts[0]

        invalid = [
            'invalid', {"prompts": ["one"]}, {"prompts": [expected[0], ""]},
            {"prompts": [expected[0], expected[1] + " <d>[Chinese] 你好！</d>"]},
            {"prompts": ["The man smiles.", expected[1] + " <d>[Chinese] 你好！</d>"]},
        ]
        for content in invalid:
            post.side_effect = [response(timeline), response(content)]
            try:
                planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Bad prompts must fail before sampling")
        post.side_effect = [response(timeline), response({}, finish="length")]
        try:
            planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings)
        except RuntimeError as error:
            assert "truncated" in str(error)
        else:
            raise AssertionError("A truncated response must not reach video sampling")
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in log_directory.glob("*.json")]
        assert any(r["finish_reason"] == "length" and r["status"] == "invalid_response" for r in reports)

        post.reset_mock()
        untimed = ["They fly over the clouds.", "They keep flying above the clouds."]
        post.side_effect = [response({"speech": []}), response({"prompts": untimed})]
        assert planner.split_prompts("They fly over the clouds.", schedule, "T2VA", 0, **settings) == (schedule, untimed)
        assert post.call_count == 2
        assert all(not clip["speech"] for clip in json.loads(post.call_args.kwargs["json"]["messages"][1]["content"])["clips"])
        for bad in [
            {"speech": [dict(speech[0], text="An invented line.")]},
            {"speech": [dict(speech[0], end_seconds=-1)]},
            {"speech": [dict(speech[0], start_seconds=float("nan"))]},
            {"speech": "none"},
        ]:
            post.side_effect = [response(bad)]
            try:
                planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Invalid speech data must fail")
        files_before = set(log_directory.iterdir())
        post.side_effect = [response(timeline), response({"prompts": expected})]
        planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **(settings | {"log_prompts": False}))
        assert set(log_directory.iterdir()) == files_before
        continuous = 'From 0-14s the speaker says <d>[Chinese] 你好！</d>.'
        post.reset_mock()
        post.side_effect = [response({"speech": [dict(speech[0], end_seconds=14)]})]
        final_schedule, final_prompts = planner.split_prompts(
            continuous, planner.segment_schedule(long.plan_segments(14, 5, 22)), 'Ref2VA', 3, **settings)
        assert len(final_schedule) == 1 and final_prompts == [continuous] and post.call_count == 1
        post.side_effect = [response({}, status=401)]
        try:
            planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **settings)
        except RuntimeError as error:
            assert "401" in str(error) and "smoke-test-placeholder" not in str(error)
        else:
            raise AssertionError("HTTP errors must propagate")
    with patch.object(planner.requests, "post") as post:
        for url in ["file:///tmp/key", "https://name:secret@example.test/v1", ""]:
            try:
                planner.split_prompts(full_prompt, schedule, "Ref2VA", 3, **(settings | {"api_url": url}))
            except ValueError as error:
                assert "API URL" in str(error) and "secret" not in str(error)
            else:
                raise AssertionError("Invalid API URLs must fail before a request")
        post.assert_not_called()
    return settings


def test_dialogue_boundaries():
    source = ('From 8 to 11 seconds, she says <d>[Chinese] 我们干一杯吧。</d>. '
              'From 11 to 14 seconds, he replies <d>[Chinese] 干杯！</d>.')
    passages = source.split('. ')
    events = [dict(text=p, start_seconds=a, end_seconds=b)
              for (a, b), p in zip([(8, 11), (11, 14)], passages)]
    schedule = planner.segment_schedule(long.plan_segments(14, 5, 22))
    plan = timing.protect_dialogue_boundaries(schedule, events, 24)
    assert plan == [(124, 0, 124), (90, 22, 68), (175, 22, 144)]
    adjusted = planner.segment_schedule(plan)
    assert adjusted[1]['final_end_seconds'] == 8
    assert adjusted[2]['final_end_seconds'] == 14
    assert sum(p[2] for p in plan) == 336
    assert all(length % 17 == 5 and keep == length - overlap for length, overlap, keep in plan[:-1])
    windows = planner.prompt_windows(adjusted, events)
    assert not windows[1]['speech']
    assert [e['local_seconds'] for e in windows[2]['speech']] == [[0.92, 3.92], [3.92, 6.92]]
    assert schedule[1]['final_end_seconds'] == 226 / 24

    for context in (5, 22, 39, 56):
        initial = planner.segment_schedule(long.plan_segments(30, 5, context))
        speech = [dict(events[0], start_seconds=3.2, end_seconds=15.3)]
        planned = timing.protect_dialogue_boundaries(initial, speech, 24)
        assert sum(p[2] for p in planned) == 720
        cursor = 0
        for length, overlap, keep in planned[:-1]:
            cursor += keep
            assert length % 17 == 5 and keep == length - overlap
            assert not round(3.2 * 24) < cursor < round(15.3 * 24)
    assert timing.protect_dialogue_boundaries(schedule, [], 24) == long.plan_segments(14, 5, 22)
    assert len(timing.protect_dialogue_boundaries(schedule, [dict(events[0], start_seconds=0, end_seconds=14)], 24)) == 1


def main():
    test_progress_scope()
    test_dialogue_boundaries()
    with tempfile.TemporaryDirectory() as log_root, \
            patch.object(folder_paths, "get_output_directory", return_value=log_root):
        api_settings = test_prompt_api()
    node = long.MiniMaxH3LongVideo
    assert tuple(node.GET_NODE_INFO_V1()["output"]) == ("VIDEO", "STRING")
    assert node.GET_NODE_INFO_V1()["input"]["optional"]["segment_seconds"][1]["default"] == 15.0
    assert long.plan_segments(14, 15, 22) == [(345, 0, 336)]
    assert len(long.plan_segments(30, 15, 22)) == 2
    plan = long.plan_segments(30, 5, 22)
    assert len(plan) == 7 and sum(keep for _, _, keep in plan) == 720
    assert long.plan_segments(14, 5, 22) == [(124, 0, 124), (124, 22, 102), (141, 22, 110)]
    schedule = planner.segment_schedule(long.plan_segments(14, 5, 22))
    assert long.plan_segments(6, 5, 22) == [(158, 0, 144)]
    for total, segment, context in [(0.1, 5, 22), (5, 5, 22), (60.1, 5, 56), (2, 0.1, 39)]:
        parts = long.plan_segments(total, segment, context)
        assert sum(p[2] for p in parts) == max(1, round(total * 24))
        assert all(length % 17 == 5 and 0 < keep <= length - overlap for length, overlap, keep in parts)
        assert all(keep == length - overlap for length, overlap, keep in parts[:-1])

    samples = []
    events = []

    def sample(noise, guider, sampler, sigmas, latent):
        index = len(samples)
        events.append(("sample", index + 1))
        long.comfy.utils.ProgressBar(1).update_absolute(1, preview="sample-preview")
        positive = guider.conditioning[0][1]
        if index:
            keyframes = positive["minimax_keyframes"]
            video_keys = [k for k in keyframes if "latent" in k]
            audio_keys = [k for k in keyframes if "audio_latent" in k]
            assert len(video_keys) == 7 and len(audio_keys) == 1
            assert all(torch.all(k["latent"] == index) for k in video_keys)
            assert torch.all(audio_keys[0]["audio_latent"] == index)
        for z in latent["samples"].unbind():
            z.fill_(index + 1)
        samples.append((noise.seed, positive))
        return io.NodeOutput(latent, latent)

    original_temp = folder_paths.get_temp_directory()
    with tempfile.TemporaryDirectory() as temp, \
            patch.object(long.BasicScheduler, "execute", return_value=io.NodeOutput(torch.tensor([1., 0.]))), \
            patch.object(long.BasicGuider, "execute", side_effect=lambda model, conditioning: io.NodeOutput(SimpleNamespace(conditioning=conditioning))), \
            patch.object(long.SamplerCustomAdvanced, "execute", side_effect=sample):
        folder_paths.set_temp_directory(temp)
        try:
            clip = Clip(events)
            updates = []
            def hook(value, total, preview, **kwargs):
                updates.append((value / total, preview))
            with patch.object(long.comfy.utils, "PROGRESS_BAR_HOOK", hook), CurrentNodeContext("smoke", "long"):
                video, preview = node.execute(None, clip, VideoVAE(events), AudioVAE(), "A continuous walk.",
                                      30, width=32, height=32, seed=100, tiled_decode=True, segment_seconds=5).result
                assert long.comfy.utils.PROGRESS_BAR_HOOK is hook
            fractions = [value for value, _ in updates]
            assert fractions[0] == 0 and fractions[-1] == 1
            assert all(a <= b for a, b in zip(fractions, fractions[1:]))
            assert all(value < 1 for value in fractions[:-1])
            assert sum(preview == "sample-preview" for _, preview in updates) == 7
            assert video.get_frame_count() == 720 and abs(video.get_duration() - 30) < 1 / 24
            assert [s[0] for s in samples] == list(range(100, 107))
            video_log, = (Path(folder_paths.get_output_directory()) / "h3_prompt_logs").glob("*_video.json")
            saved = json.loads(video_log.read_text(encoding="utf-8"))
            assert saved["prompts"] == ["A continuous walk."] * 7
            assert saved["seeds"] == [s[0] for s in samples]
            assert saved["prompt_id"] == "smoke" and saved["node_id"] == "long"
            assert saved["status"] == "prepared"
            assert len(clip.calls) == 1
            assert events == [("encode", "A continuous walk.")] + [
                (stage, index) for group in ((1, 2, 3), (4, 5, 6), (7,))
                for stage in ("sample", "decode") for index in group
            ]
            components = video.get_components()
            assert components.images.shape[0] == 720 and components.audio["sample_rate"] == 32000
            cursor = 0
            for index, (_, _, keep) in enumerate(plan):
                value = (index + 1) / 10
                for frame in (cursor, cursor + keep - 1):
                    assert abs(float(components.images[frame].mean()) - value) < 0.03
                cursor += keep
            assert not list(Path(temp).glob("h3_segments_*"))
            del components

            samples.clear()
            clip = Clip()
            first = torch.zeros(1, 32, 32, 3)
            node.execute(None, clip, VideoVAE(), AudioVAE(), "Walk.", 7,
                         width=32, height=32, first_frame=first, tiled_decode=False, segment_seconds=5)
            assert len(clip.calls) == 2
            assert len(clip.calls[0]["images"]) == 1 and not clip.calls[1]["images"]

            samples.clear()
            clip = Clip()
            node.execute(None, clip, VideoVAE(), AudioVAE(), "<Picture 1> walks.", 7,
                         width=32, height=32, first_frame=first, reference_images=first.repeat(2, 1, 1, 1), segment_seconds=5)
            assert len(clip.calls) == 1
            assert all(len(s[1]["minimax_refs"]) == 2 for s in samples)
            assert len(samples[0][1]["minimax_keyframes"]) == 1

            full_prompt = "detailed_description: [Shot 1] A continuous 14-second dinner conversation."
            def adapt(prompt, schedule, mode, reference_count, **settings):
                assert prompt == full_prompt and settings == api_settings
                assert schedule == planner.segment_schedule(long.plan_segments(14, segment_seconds, 22))
                assert mode == expected_mode and reference_count == expected_refs
                return schedule, [f"Segment {s['segment']}: continue dinner." for s in schedule]

            for segment_seconds, expected_count, expected_mode, expected_refs in [
                (5.0, 3, "Ref2VA", 3), (5.5, 3, "I2VA", 0), (5.0, 3, "T2VA", 0),
            ]:
                samples.clear()
                events.clear()
                clip = Clip(events)
                vae = VideoVAE(events)
                with patch.object(long, "split_prompts", side_effect=adapt) as split:
                    video, preview = node.execute(
                        None, clip, vae, AudioVAE(), full_prompt, 14,
                        width=32, height=32, segment_seconds=segment_seconds,
                        first_frame=first if expected_mode != "T2VA" else None,
                        reference_images=first.repeat(expected_refs, 1, 1, 1) if expected_refs else None,
                        prompt_api=api_settings).result
                    split.assert_called_once()
                assert len(samples) == expected_count and video.get_frame_count() == 336
                assert clip.texts == [f"Segment {i + 1}: continue dinner." for i in range(expected_count)]
                assert events == [("encode", text) for text in clip.texts] + [
                    (stage, index + 1) for stage in ("sample", "decode") for index in range(expected_count)
                ]
                assert f"Segment {expected_count} | final" in preview and "smoke-test-placeholder" not in preview
                if expected_refs:
                    assert all(len(s[1]["minimax_refs"]) == expected_refs for s in samples)
                    assert all(s[1]["minimax_refs"] is samples[0][1]["minimax_refs"] for s in samples)
                    assert vae.encode_calls == expected_refs + 1
                    assert all(len(c["minimax_ref_items"]) == expected_refs for c in clip.calls)
                    assert len(samples[0][1]["minimax_keyframes"]) == 1

            samples.clear()
            adjusted = planner.segment_schedule([(124, 0, 124), (90, 22, 68), (175, 22, 144)])
            with patch.object(long, "split_prompts", return_value=(adjusted, ["Greeting.", "Eating.", "Toast."])):
                video, preview = node.execute(
                    None, Clip(), VideoVAE(), AudioVAE(), full_prompt, 14,
                    width=32, height=32, segment_seconds=5, prompt_api=api_settings).result
            assert len(samples) == 3 and video.get_frame_count() == 336
            assert 'final 8.000-14.000s' in preview and 'sampled 7.292s' in preview

            samples.clear()
            clip = Clip()
            with patch.object(long, "split_prompts") as split:
                node.execute(None, clip, VideoVAE(), AudioVAE(), full_prompt, 14,
                             width=32, height=32, prompt_api=api_settings)
                split.assert_not_called()
                assert clip.texts == [full_prompt]

            samples.clear()
            with patch.object(long, "split_prompts") as split:
                node.execute(None, Clip(), VideoVAE(), AudioVAE(), full_prompt, 14,
                             width=32, height=32, segment_seconds=5)
                split.assert_not_called()
                assert len(samples) == 3

            samples.clear()
            with patch.object(long, "split_prompts", side_effect=RuntimeError("API failed")):
                try:
                    node.execute(None, Clip(), VideoVAE(), AudioVAE(), full_prompt, 14,
                                 width=32, height=32, prompt_api=api_settings, segment_seconds=5)
                except RuntimeError as error:
                    assert str(error) == "API failed"
                else:
                    raise AssertionError("API failure must propagate before sampling")
                assert not samples

            files_before = set(Path(temp).iterdir())
            samples.clear()

            def fail_second_segment(*args):
                if samples:
                    raise RuntimeError("cancelled")
                return sample(*args)

            with patch.object(long.SamplerCustomAdvanced, "execute", side_effect=fail_second_segment):
                try:
                    node.execute(None, Clip(), VideoVAE(), AudioVAE(), "Walk.", 7, width=32, height=32, segment_seconds=5)
                except RuntimeError as error:
                    assert str(error) == "cancelled"
                else:
                    raise AssertionError("Sampling failure must propagate")
            assert set(Path(temp).iterdir()) == files_before
        finally:
            folder_paths.set_temp_directory(original_temp)
    print("PASS: registration, 15s default, frame planning, plain JSON prompt planning, speech/dialogue validation, credential-safe logs, API bypass, grouped encoding/sampling, cross-group latent/audio continuation, real MP4 frame order, overall progress and hook cleanup, reference reuse, failure cleanup")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as output_root, patch.object(folder_paths, "get_output_directory", return_value=output_root):
        main()
