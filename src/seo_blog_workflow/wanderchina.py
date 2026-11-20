"""Build a review bundle for WanderChina without modifying its checkout."""
import json
import math
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def export_bundle(db, keyword, destination, timezone="Asia/Shanghai"):
    row = db.execute("SELECT article,output_path FROM keywords WHERE keyword=?", (keyword,)).fetchone()
    if not row or not row["article"] or not row["output_path"]:
        raise ValueError("Exported article required")
    article = json.loads(row["article"])
    source = Path(row["output_path"]).parent
    image = source / "cover.png"
    if not image.is_file():
        raise ValueError("Generated PNG cover required")
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    if not slug:
        raise ValueError("ASCII route slug required")
    body = re.sub(r"^# .+\n", "", article["body"], count=1)
    parts = re.split(r"^## (.+)$", body, flags=re.M)
    sections = []
    if parts[0].strip():
        sections.append({"heading":"Overview", "paragraphs":[], "markdown":parts[0].strip()})
    for index in range(1, len(parts), 2):
        sections.append({"heading":parts[index], "paragraphs":[], "markdown":parts[index+1].strip()})
    date = datetime.now(ZoneInfo(timezone)).date().isoformat()
    guide = {"slug":slug, "title":article["title"], "description":article["description"],
             "category":"Transport", "image":f"assets/guides/{slug}/cover.png",
             "image_alt":"Conceptual illustration comparing high-speed rail and air travel between Shanghai and Beijing",
             "published":date, "updated":date, "read_minutes":max(1, math.ceil(len(body.split())/200)),
             "featured":False, "sections":sections}
    output = Path(destination)
    content = output / "content/guides" / (slug + ".json")
    target = output / "dist" / guide["image"]
    if content.exists() or target.exists():
        raise FileExistsError("Bundle already exists; choose another destination")
    content.parent.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    content.write_text(json.dumps(guide, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(image, target)
    return {"bundle":str(output), "route":"/guide/" + slug + "/", "renderer_support_required":True,
            "note":"Dates are preview values; set actual first-publication date on release. Nothing published."}
