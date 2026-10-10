"""Reference pictures and prompt text with local backup and loading."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import uuid

from aiohttp import web
from PIL import Image

import folder_paths
from comfy_api.latest import io
from server import PromptServer

from .csrf_guard import require_same_origin
from .prompt_builder import load_pictures, picture_paths


def backup_directory():
    return Path(folder_paths.get_output_directory()).resolve() / "h3_prompt_backups"


def save_backup(prompt, pictures):
    if not isinstance(prompt, str):
        raise ValueError("Prompt must be text.")
    if not isinstance(pictures, list) or any(not isinstance(name, str) for name in pictures):
        raise ValueError("Pictures must be a list of file names.")
    sources = [Path(folder_paths.get_annotated_filepath(name)) for name in pictures]
    root = backup_directory()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    destination = root / (now.strftime("%Y%m%d_%H%M%SZ_") + uuid.uuid4().hex[:8])
    with TemporaryDirectory(prefix=".pending_", dir=root) as staging:
        staging = Path(staging)
        entries = []
        for index, source in enumerate(sources, 1):
            with Image.open(source) as image:
                suffix = source.suffix.lower()
                if Image.registered_extensions().get(suffix) != image.format:
                    suffix = "." + image.format.lower()
                image.verify()
            filename = f"Picture_{index:02d}{suffix}"
            saved = staging / filename
            shutil.copyfile(source, saved)
            with saved.open("rb") as file:
                digest = hashlib.file_digest(file, "sha256").hexdigest()
            entries.append({"label": f"<Picture {index}>", "file": filename,
                            "source": pictures[index - 1], "sha256": digest})
        (staging / "prompt.txt").write_text(prompt, encoding="utf-8", newline="")
        (staging / "manifest.json").write_text(json.dumps({
            "created_at": now.isoformat(), "prompt_file": "prompt.txt", "images": entries,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        staging.rename(destination)
    return {"directory": str(root), "backup_path": str(destination), "image_count": len(sources)}


def backup_child(directory, name):
    if not isinstance(name, str) or name in ("", ".", "..") or any(char in name for char in "/\\:"):
        raise ValueError("Invalid backup file name.")
    path = directory / name
    if not folder_paths.is_within_directory(str(directory), str(path)):
        raise ValueError("Backup path is outside the backup folder.")
    return path


def read_backup(backup_id):
    directory = backup_child(backup_directory(), backup_id)
    manifest = json.loads(backup_child(directory, "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("images"), list):
        raise ValueError("Invalid backup image manifest.")
    pictures = []
    for entry in manifest["images"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid backup image entry.")
        path = backup_child(directory, entry.get("file"))
        if not path.is_file():
            raise FileNotFoundError(f"Backup image is missing: {path.name}")
        pictures.append(f"h3_prompt_backups/{backup_id}/{path.name} [output]")
    with backup_child(directory, "prompt.txt").open(encoding="utf-8", newline="") as file:
        prompt = file.read()
    return {"id": backup_id, "created_at": manifest.get("created_at", ""),
            "backup_path": str(directory), "prompt": prompt, "pictures": pictures}


def list_backups():
    root = backup_directory()
    if not root.exists():
        return []
    entries = []
    for directory in sorted(root.iterdir(), reverse=True):
        if not directory.is_dir() or directory.name.startswith("."):
            continue
        try:
            item = read_backup(directory.name)
        except (ValueError, OSError) as error:
            entries.append({"id": directory.name, "error": str(error)})
            continue
        entries.append({"id": item["id"], "created_at": item["created_at"],
                        "image_count": len(item["pictures"]), "cover": next(iter(item["pictures"]), None),
                        "prompt_preview": item["prompt"][:180]})
    return entries


def register_backup_routes():
    server = getattr(PromptServer, "instance", None)
    if server is None or getattr(register_backup_routes, "_done", False):
        return

    @server.routes.get("/h3_motion_context/prompt_backup")
    async def _backup_directory(request):
        return web.json_response({"directory": str(backup_directory())})

    @server.routes.get("/h3_motion_context/prompt_backups")
    async def _list_backups(request):
        try:
            entries = await asyncio.to_thread(list_backups)
        except OSError as error:
            return web.json_response({"error": str(error)}, status=400)
        return web.json_response({"backups": entries})

    @server.routes.get("/h3_motion_context/prompt_backups/{backup_id}")
    async def _read_backup(request):
        try:
            result = await asyncio.to_thread(read_backup, request.match_info["backup_id"])
        except (ValueError, OSError) as error:
            return web.json_response({"error": str(error)}, status=400)
        return web.json_response(result)

    @server.routes.post("/h3_motion_context/prompt_backup")
    @require_same_origin
    async def _save_backup(request):
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError("Backup request must be a JSON object.")
            result = await asyncio.to_thread(save_backup, data.get("prompt", ""), data.get("pictures", []))
        except (ValueError, OSError, SyntaxError, Image.DecompressionBombError) as error:
            return web.json_response({"error": str(error)}, status=400)
        return web.json_response(result)

    register_backup_routes._done = True


class MiniMaxH3PromptBackup(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="MiniMaxH3PromptBackup", display_name="H3 Image & Prompt",
            category="video/minimax", is_output_node=True,
            description="Edit and output images and a prompt. backup saves to output/h3_prompt_backups; load previews and restores a backup.",
            inputs=[io.String.Input("pictures", default="[]"),
                    io.String.Input("prompt", default="", multiline=True)],
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
    def execute(cls, pictures="[]", prompt=""):
        return io.NodeOutput(prompt, load_pictures(picture_paths(pictures)))


NODE_CLASS_MAPPINGS = {"MiniMaxH3PromptBackup": MiniMaxH3PromptBackup}
NODE_DISPLAY_NAME_MAPPINGS = {"MiniMaxH3PromptBackup": "H3 Image & Prompt"}
