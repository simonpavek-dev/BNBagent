"""Načítání znalostní báze z YAML souborů."""
import yaml

from . import config

APARTMANY_DIR = config.ZNALOSTI_DIR / "apartmany"


def _pro_model(text):
    """Výchozí kód keyboxu model nevidí – dostane vždy dopočítaný kód pro konkrétní rezervaci."""
    return "\n".join(l for l in text.splitlines() if "keybox_kod" not in l)


def obecne_text():
    return (config.ZNALOSTI_DIR / "obecne.yaml").read_text(encoding="utf-8")


def obecne():
    return yaml.safe_load(obecne_text()) or {}


def apartman_podle_souboru(nazev):
    """Vrátí (data, text) apartmánu podle názvu souboru bez .yaml, např. 'apt-01'."""
    path = APARTMANY_DIR / f"{nazev}.yaml"
    if not path.exists():
        return None, None
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}, _pro_model(text)


def apartman_podle_smoobu_id(smoobu_id):
    """Najde soubor apartmánu, jehož smoobu_id odpovídá. Soubory začínající '_' se přeskakují."""
    for path in sorted(APARTMANY_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if str(data.get("smoobu_id") or "").strip() == str(smoobu_id):
            return data, _pro_model(text)
    return None, None


def vsechny_apartmany():
    out = []
    for path in sorted(APARTMANY_DIR.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        out.append((path.stem, yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    return out
