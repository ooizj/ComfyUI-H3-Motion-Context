"""Keep speech intact on H3's frame grid and check adapted prompts."""

from collections import Counter
import math
import re

from comfy_extras.nodes_minimax_h3 import align_frame_count


_DIALOGUE = re.compile(r"<d>(.*?)</d>", re.DOTALL)
FULL_WIDTH_SPEAKER = re.compile(r"（(S\d+)）")
FIRST_FRAME_INSTRUCTION = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."


def dialogue_lines(text):
    return Counter(line.strip() for line in _DIALOGUE.findall(text))


def validate_timeline(timeline, source):
    events = timeline.get("speech") if isinstance(timeline, dict) else None
    if not isinstance(events, list):
        raise RuntimeError("LLM must return a speech list.")
    for event in events:
        if not isinstance(event, dict):
            raise RuntimeError("LLM returned an invalid speech range.")
        passage = event.get("text")
        if not isinstance(passage, str) or not passage.strip() or passage not in source:
            raise RuntimeError("LLM speech text was changed or is missing from the original prompt.")
        start, end = event.get("start_seconds"), event.get("end_seconds")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < 0 or end <= start):
            raise RuntimeError("LLM returned invalid speech start/end seconds.")
    return events


def protect_dialogue_boundaries(schedule, events, fps):
    ranges = [(round(e["start_seconds"] * fps), round(e["end_seconds"] * fps))
              for e in events]
    original = [(s["sampled_frames"], s["overlap_frames"], s["retained_frames"]) for s in schedule]
    if not ranges:
        return original
    cursor = 0
    for _, _, keep in original[:-1]:
        cursor += keep
        if any(a < cursor < b for a, b in ranges):
            break
    else:
        return original

    total = sum(s[2] for s in original)
    target = original[0][0]
    context = original[1][1]
    tail_limit = align_frame_count(target + fps)
    plan, cursor = [], 0
    while cursor < total:
        overlap = context if plan else 0
        tail = align_frame_count(max(5, total - cursor + overlap))
        length = tail if tail <= tail_limit else target
        minimum = align_frame_count(max(5, overlap + fps))
        # Intermediate tails must stay on H3's 17-frame grid: the next clip
        # reads the actual latent tail, so trimming an intermediate tail is wrong.
        for delta in range(0, max(tail - length, length) + 17, 17):
            candidates = (length + delta, length - delta) if delta else (length,)
            chosen = None
            for candidate in candidates:
                if candidate > tail or (candidate < minimum and candidate != tail):
                    continue
                end = min(total, cursor + candidate - overlap)
                if end == total or not any(a < end < b for a, b in ranges):
                    chosen = candidate
                    break
            if chosen is not None:
                break
        keep = min(total - cursor, chosen - overlap)
        plan.append((chosen, overlap, keep))
        cursor += keep
    return plan


def validate_prompts(prompts, schedule, events, source, input_mode):
    if (not isinstance(prompts, list) or len(prompts) != len(schedule)
            or any(not isinstance(p, str) or not p.strip() for p in prompts)):
        raise RuntimeError(f"LLM must return {len(schedule)} nonempty prompts.")
    if dialogue_lines(source) != dialogue_lines("\n".join(prompts)):
        raise RuntimeError("LLM changed, omitted or repeated quoted <d> dialogue. Change variation and retry.")
    owners = {}
    for event in events:
        for index, segment in enumerate(schedule, 1):
            if segment["final_start_seconds"] <= event["start_seconds"] < segment["final_end_seconds"]:
                for line in _DIALOGUE.findall(event["text"]):
                    owners.setdefault(line.strip(), set()).add(index)
    for index, prompt in enumerate(prompts, 1):
        if any(line.strip() in owners and index not in owners[line.strip()]
               for line in _DIALOGUE.findall(prompt)):
            raise RuntimeError("LLM moved quoted dialogue outside its assigned segment. Change variation and retry.")
    prompts = [FULL_WIDTH_SPEAKER.sub(r"(\1)", prompt) for prompt in prompts]
    if input_mode == "I2VA":
        prompts[0] = FIRST_FRAME_INSTRUCTION + "\n\n" + prompts[0]
    return prompts
