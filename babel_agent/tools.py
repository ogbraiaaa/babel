"""Explicit capabilities. No shell execution or access outside the workspace."""

import json
import platform
from datetime import datetime
from pathlib import Path


def definition(name, description, properties=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {},
                       "required": required or [], "additionalProperties": False}}}


STRING = {"type": "string"}
DEFINITIONS = [
    definition("list_files", "Lista arquivos e pastas na área de trabalho.", {"path": STRING}),
    definition("read_file", "Lê um arquivo de texto UTF-8 de até 64 KiB.", {"path": STRING}, ["path"]),
    definition("create_file", "Propõe criar um arquivo UTF-8 novo. Requer aprovação humana. Nunca sobrescreve.",
               {"path": STRING, "content": STRING}, ["path", "content"]),
    definition("move_file", "Propõe mover ou renomear um arquivo dentro da área de trabalho. Requer aprovação.",
               {"source": STRING, "destination": STRING}, ["source", "destination"]),
    definition("system_info", "Consulta sistema operacional e data/hora local."),
]
WRITES = {"create_file", "move_file"}


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, value):
        if not isinstance(value, str) or not value or len(value) > 512:
            raise ValueError("Caminho inválido.")
        relative = Path(value)
        # Reject Windows alternate data streams and cross-platform absolute paths.
        if relative.is_absolute() or ":" in value or "\\" in value:
            raise ValueError("Use caminhos relativos com / dentro da área de trabalho.")
        candidate = self.root / relative
        for part in [candidate, *candidate.parents]:
            if part == self.root:
                break
            if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
                raise ValueError("Links e junções não são permitidos.")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("O caminho está fora da área de trabalho.")
        return resolved

    def validate(self, name, args):
        spec = next((d["function"] for d in DEFINITIONS if d["function"]["name"] == name), None)
        if not spec or not isinstance(args, dict):
            raise ValueError("Ferramenta ou argumentos inválidos.")
        params = spec["parameters"]
        if set(args) - set(params["properties"]) or set(params["required"]) - set(args):
            raise ValueError("Argumentos ausentes ou desconhecidos.")
        if any(not isinstance(v, str) for v in args.values()):
            raise ValueError("Argumentos devem ser texto.")
        for key in ("path", "source", "destination"):
            if key in args:
                self.path(args[key])
        if len(args.get("content", "").encode("utf-8")) > 65536:
            raise ValueError("Conteúdo excede 64 KiB.")

    def execute(self, name, args, *, approved=False):
        self.validate(name, args)
        if name in WRITES and not approved:
            raise ValueError("Esta ação exige aprovação.")
        if name == "list_files":
            folder = self.path(args.get("path", "."))
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
            return {"entries": [{"name": p.name, "directory": p.is_dir()} for p in entries[:200]],
                    "truncated": len(entries) > 200}
        if name == "read_file":
            with self.path(args["path"]).open("rb") as stream:
                data = stream.read(65537)
            if len(data) > 65536:
                raise ValueError("Arquivo excede 64 KiB.")
            return {"content": data.decode("utf-8")}
        if name == "create_file":
            target = self.path(args["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as stream:
                stream.write(args["content"])
            return {"created": args["path"]}
        if name == "move_file":
            source, target = self.path(args["source"]), self.path(args["destination"])
            if not source.is_file():
                raise ValueError("A origem deve ser um arquivo.")
            # Exclusive destination creation avoids overwriting on every platform.
            data = source.read_bytes() if source.stat().st_size <= 65536 else None
            if data is None:
                raise ValueError("Mover arquivos está limitado a 64 KiB nesta versão.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            source.unlink()
            return {"moved": args["source"], "destination": args["destination"]}
        return {"system": platform.system(), "release": platform.release(),
                "time": datetime.now().astimezone().isoformat(timespec="seconds")}

    def result(self, name, args, *, approved=False):
        try:
            return json.dumps(self.execute(name, args, approved=approved), ensure_ascii=False)
        except (OSError, ValueError) as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
