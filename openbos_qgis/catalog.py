from pathlib import Path
import os
import re

_ESCAPE_RE = re.compile(r"#U([0-9a-fA-F]{4,6})")


def decode_name(text: str) -> str:
    return _ESCAPE_RE.sub(lambda match: chr(int(match.group(1), 16)), text)


class SymbolCatalog:
    ELECTRO_ROOT = "thw elektroversorgung"

    def __init__(self, svg_dir: Path):
        self.svg_dir = Path(svg_dir)
        self.categories = {}

    def load(self):
        if not self.svg_dir.is_dir():
            raise FileNotFoundError(f"SVG-Bibliothek fehlt: {self.svg_dir}")
        result = {}
        for path in sorted(self.svg_dir.rglob("*.svg"), key=lambda p: str(p).casefold()):
            relative = path.relative_to(self.svg_dir)
            category = decode_name(str(relative.parent).replace(os.sep, " / "))
            name = decode_name(path.stem).replace("_", " ")
            entry = {
                "name": name,
                "category": category,
                "path": str(path),
                "electro": self.is_electro_category(category),
            }
            result.setdefault(category, []).append(entry)
        if not result:
            raise RuntimeError("Keine SVG-Zeichen in der Bibliothek gefunden.")
        self.categories = result
        return self

    @classmethod
    def is_electro_category(cls, category: str) -> bool:
        root = str(category or "").split(" / ", 1)[0]
        normalized = root.replace("_", " ").strip().casefold()
        return normalized == cls.ELECTRO_ROOT

    def category_names(self, electro: bool):
        names = []
        for category, entries in self.categories.items():
            if any(bool(entry["electro"]) == electro for entry in entries):
                names.append(category)
        return sorted(names, key=str.casefold)

    def iter_entries(self, electro: bool, category=None, query=""):
        query = str(query or "").strip().casefold()
        categories = [category] if category else self.category_names(electro)
        for category_name in categories:
            for entry in self.categories.get(category_name, []):
                if bool(entry["electro"]) != electro:
                    continue
                if query and query not in f"{entry['name']} {category_name}".casefold():
                    continue
                yield entry
