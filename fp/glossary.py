"""Glossary: definitions live once in config/glossary.json and render into popovers and the glossary section."""
import html
import re

from .common import ROOT, load_json

E = html.escape
_G = None


def glossary():
    global _G
    if _G is None:
        _G = load_json(ROOT / "config" / "glossary.json")
    return _G


def term(key, label=None):
    """Inline jargon term; a button so it is focusable and tappable. KeyError on unknown keys."""
    t = glossary()["terms"][key]
    return f'<button type="button" class="term" data-term="{E(key)}" aria-expanded="false">{E(label or t["term"])}</button>'


def expand(text):
    """Replace {{t:key}} / {{t:key|label}} tokens in template text."""
    return re.sub(r"\{\{t:([a-z0-9_]+)(?:\|([^}]*))?\}\}", lambda m: term(m.group(1), m.group(2)), text)


def popover_data():
    return {k: {"term": v["term"], "def": v["def"]} for k, v in glossary()["terms"].items()}


def glossary_html():
    g = glossary()
    out = []
    for i, grp in enumerate(g["groups"]):
        items = "".join(f'<dt id="g-{E(k)}">{E(v["term"])}</dt><dd>{E(v["def"])}</dd>'
                        for k, v in g["terms"].items() if v["group"] == grp)
        out.append(f'<details class="gloss"{" open" if i == 0 else ""}><summary>{E(grp)}</summary><dl>{items}</dl></details>')
    return "\n".join(out)
