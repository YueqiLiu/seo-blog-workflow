"""Optional OpenAI-compatible base64 image adapter and deterministic SVG cards."""
import base64
import html
import textwrap
from pathlib import Path
from .runtime import ModelAPI
from .files import atomic_write


def saved_cover(settings, directory):
    mode = settings.get('mode', 'none')
    if mode == 'none':
        return None
    extension = {'template': 'svg', 'api': 'png'}.get(mode)
    if extension is None:
        raise ValueError('Image mode must be none, template or api')
    path = Path(directory) / ('cover.' + extension)
    if not path.is_file():
        return None
    data = path.read_bytes()
    if extension == 'png':
        return path if len(data) > 8 and data.startswith(b'\x89PNG\r\n\x1a\n') else None
    from xml.etree import ElementTree
    try:
        root = ElementTree.fromstring(data)
        return path if root.tag in {'svg', '{http://www.w3.org/2000/svg}svg'} else None
    except ElementTree.ParseError:
        return None


def cover_prompt(article, settings):
    """Use article context and optional user art direction, never a fixed industry."""
    context = article.get("image_prompt") or article["title"]
    return (
        "Create an editorial illustration for this article: " + article["title"] +
        ". Article visual brief: " + context +
        ". Art direction: " + settings.get("art_direction", "Clear focal point, spacious composition, refined editorial style") +
        ". Wide 16:9 composition. No text or logos, fabricated statistics, misleading maps or fake product screenshots. "
        "Represent the article topic specifically. Clearly an illustration, not documentary evidence."
    )


def create_image(settings, article, directory):
    mode = settings.get("mode", "none")
    if mode == "none":
        return None
    directory = Path(directory)
    if mode == "template":
        lines = textwrap.wrap(article["title"], width=32)[:5]
        text = "".join(f'<text x="80" y="{160 + i * 75}" font-size="56" fill="#102438">{html.escape(line)}</text>' for i, line in enumerate(lines))
        path = directory / "cover.svg"
        atomic_write(path, '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675"><rect width="1200" height="675" rx="32" fill="#f4faff"/><rect x="40" y="40" width="1120" height="595" rx="24" fill="none" stroke="#bbd4ed" stroke-width="3"/>' + text + '</svg>')
        return path
    if mode != "api":
        raise ValueError("Image mode must be none, template or api")
    payload = {
        "model": settings["model"], "prompt": article.get("image_prompt") or article["title"],
        "size": settings.get("size", "1536x1024"), "n": 1}
    if settings.get("provider") != "aisa":
        payload["response_format"] = "b64_json"
    response = ModelAPI(settings).request("/images/generations", payload)
    encoded = response["data"][0].get("b64_json")
    if not encoded:
        raise ValueError("Image provider must return b64_json; URL and async adapters are not implemented")
    data = base64.b64decode(encoded, validate=True)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Image provider must return PNG")
    path = directory / "cover.png"
    atomic_write(path, data)
    return path


def generate_cover(db, config, keyword):
    import json
    import re
    row = db.execute("SELECT article,output_path FROM keywords WHERE keyword=?", (keyword,)).fetchone()
    if not row or not row["article"] or not row["output_path"]:
        raise ValueError("An exported article is required")
    path = Path(row["output_path"])
    settings = config.get('cover_test', config.get('images', {}))
    if settings.get('mode') != 'api':
        raise ValueError('generate-cover requires images.mode=api or cover_test.mode=api')
    target = path.parent / "cover.png"
    reused = saved_cover(settings, path.parent) is not None
    article = json.loads(row["article"])
    article["image_prompt"] = cover_prompt(article, settings)
    if not reused:
        target = create_image(settings, article, path.parent)
    content = path.read_text(encoding="utf-8")
    front, body = content.split("\n---\n", 1)
    front = re.sub(r'^image:.*$', 'image: "cover.png"', front, flags=re.M)
    if not re.search(r"^image:", front, re.M):
        front += '\nimage: "cover.png"'
    atomic_write(path, front + "\n---\n" + body)
    return {"image": str(target), "reused": reused, "article_updated": str(path)}
