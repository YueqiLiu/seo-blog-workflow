"""Portable editorial checks; passing these does not establish factual accuracy."""
import re


def audit(article, website):
    body = article.get("body", "")
    issues = []
    if len(re.findall(r"^# \S", body, re.M)) != 1:
        issues.append("Require exactly one H1")
    if len(article.get("title", "")) > 60:
        issues.append("SEO title exceeds configured default of 60 characters")
    if not 55 <= len(article.get("description", "")) <= 160:
        issues.append("Meta description must contain 55–160 characters")
    if len(re.findall(r"^## \S", body, re.M)) < 3:
        issues.append("Require at least three useful H2 sections")
    if not re.search(r"^## .*?(FAQ|frequently asked)", body, re.M | re.I):
        issues.append("Missing FAQ section")
    else:
        faq = re.split(r"^## .*?(?:FAQ|frequently asked).*?$", body, flags=re.M | re.I)[-1]
        faq = re.split(r"^## ", faq, flags=re.M)[0]
        if len(re.findall(r"^### .+\?\s*$", faq, re.M)) < 3:
            issues.append("FAQ requires at least three question headings")
    if website not in re.findall(r"\]\((https?://[^\s)]+)\)", body):
        issues.append("Missing product website link")
    for phrase in ("not independently verified here", "site appears to focus", "unverified_owner_review_required"):
        if phrase in body.lower():
            issues.append("Internal profile uncertainty leaked into reader copy")
            break
    return issues


def repair_article(api, article, product, candidate, language, max_attempts=2):
    """Repair boundedly and return the last draft even when checks still fail."""
    import json
    current = dict(article)
    for _ in range(max_attempts):
        issues = audit(current, product["website"])
        if not issues:
            break
        revised = api.structured(writing_prompt(product, candidate, language) +
            "\nRevise this existing draft to fix these issues: " + json.dumps(issues) +
            "\nPreserve verified facts, links and sources. Do not invent evidence. "
            "Improve specificity and natural flow. Existing draft: " + json.dumps(current))
        if not all(isinstance(revised.get(key), str) and revised[key].strip()
                   for key in ("title", "description", "body")):
            raise ValueError("Repair returned invalid article fields")
        current = revised
    return current, audit(current, product["website"])


def writing_prompt(product, candidate, language):
    import json
    return (
        "Write an original, specific SEO article that directly answers the keyword intent. "
        "Return JSON fields title, description, body (Markdown), image_prompt. "
        "Title maximum 60 characters; description 55–160 characters. "
        "Use exactly one H1, at least three useful H2 sections, a conclusion and "
        "an FAQ section with at least three real questions and answers. "
        "Give concrete decision criteria and useful examples, not generic advice. "
        "For transport queries compare actual transport modes explicitly. "
        "Do not invent prices, schedules, policies, statistics, firsthand experience or citations. "
        "If current facts are unavailable omit specifics and retain a concise verification note. "
        "Include one natural product website link without claiming unverified services. "
        "Product profile status and verification limitations are INTERNAL instructions: "
        "do not describe the site as unverified or say it appears to focus on a topic in public copy. "
        "Do not fabricate capabilities to compensate. "
        "Product: " + json.dumps(product) + "\nResearch: " + json.dumps(candidate) +
        "\nLanguage: " + language
    )
