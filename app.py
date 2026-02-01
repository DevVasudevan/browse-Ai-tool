import json
import os
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TOOLS_PATH = DATA_DIR / "tools.json"
SUBMISSIONS_PATH = DATA_DIR / "submissions.json"

CATEGORIES = [
    "Resume & Career",
    "Marketing & Social Media",
    "Design & Images",
    "Video & Audio",
    "Coding & Development",
    "Business & Analytics",
    "Chatbots & Automation",
    "Education & Learning",
]

PRICING_TYPES = ["Free", "Freemium", "Paid"]
SORT_OPTIONS = ["popularity", "trending", "new"]


def create_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)

    @app.get("/")
    def home():
        tools = load_tools()
        featured = sorted(tools, key=lambda t: t.get("popularity", 0), reverse=True)[:6]
        trending = sorted(tools, key=lambda t: t.get("trending", 0), reverse=True)[:6]

        return render_template(
            "index.html",
            categories=CATEGORIES,
            featured=featured,
            trending=trending,
            meta={
                "title": "AI Tool Marketplace — Discover the best AI tools",
                "description": "Find the perfect AI tool for your task with curated categories, filters, and smart recommendations.",
                "path": url_for("home"),
            },
        )

    @app.get("/tools")
    def tools_index():
        tools = load_tools()

        q = (request.args.get("q") or "").strip()
        category = (request.args.get("category") or "").strip()
        pricing = (request.args.get("pricing") or "").strip()
        sort = (request.args.get("sort") or "popularity").strip().lower()

        tools = apply_filters(tools, q=q, category=category, pricing=pricing)
        tools = apply_sort(tools, sort)

        return render_template(
            "tools.html",
            tools=tools,
            categories=CATEGORIES,
            pricing_types=PRICING_TYPES,
            sort_options=SORT_OPTIONS,
            selected={"q": q, "category": category, "pricing": pricing, "sort": sort},
            meta={
                "title": "Browse AI Tools — AI Tool Marketplace",
                "description": "Explore AI tools by category, pricing, and popularity. Discover the best AI tools for your workflow.",
                "path": url_for("tools_index"),
            },
        )

    @app.get("/tools/<slug>")
    def tool_detail(slug: str):
        tool = get_tool_by_slug(slug)
        if not tool:
            abort(404)

        return render_template(
            "tool_detail.html",
            tool=tool,
            meta={
                "title": f"{tool['name']} — AI Tool Marketplace",
                "description": tool.get("description") or "AI tool details, pricing, and best use cases.",
                "path": url_for("tool_detail", slug=slug),
            },
        )

    @app.route("/submit", methods=["GET", "POST"])
    def submit_tool():
        if request.method == "GET":
            return render_template(
                "submit.html",
                categories=CATEGORIES,
                pricing_types=PRICING_TYPES,
                meta={
                    "title": "Submit an AI Tool — AI Tool Marketplace",
                    "description": "Submit your AI tool for review. No login required.",
                    "path": url_for("submit_tool"),
                },
            )

        payload = {
            "submitted_at": datetime.utcnow().isoformat() + "Z",
            "name": (request.form.get("name") or "").strip(),
            "url": (request.form.get("url") or "").strip(),
            "description": (request.form.get("description") or "").strip(),
            "category": (request.form.get("category") or "").strip(),
            "pricing_type": (request.form.get("pricing_type") or "").strip(),
            "email": (request.form.get("email") or "").strip(),
        }

        if not payload["name"] or not payload["url"]:
            return redirect(url_for("submit_tool", error="missing"))

        save_submission(payload)
        send_submission_email(payload)  # Send email notification
        return redirect(url_for("submit_tool", success="1"))

    @app.post("/api/recommend")
    def recommend():
        body = request.get_json(silent=True) or {}
        task = (body.get("task") or "").strip()

        if not task:
            return jsonify({"tools": [], "reason": "missing_task"})

        tools = load_tools()

        # Priority: OpenAI -> Gemini -> keyword fallback
        recommended_slugs = (
            recommend_with_openai(task, tools)
            or recommend_with_gemini(task, tools)
            or recommend_with_keywords(task, tools)
        )

        tool_by_slug = {t["slug"]: t for t in tools}
        result = [tool_by_slug[s] for s in recommended_slugs if s in tool_by_slug]

        return jsonify({"tools": result, "task": task})

    @app.get("/privacy")
    def privacy():
        return render_template(
            "privacy.html",
            meta={
                "title": "Privacy Policy — AI Tool Marketplace",
                "description": "Privacy policy for AI Tool Marketplace.",
                "path": url_for("privacy"),
            },
        )

    @app.get("/terms")
    def terms():
        return render_template(
            "terms.html",
            meta={
                "title": "Terms & Conditions — AI Tool Marketplace",
                "description": "Terms and conditions for AI Tool Marketplace.",
                "path": url_for("terms"),
            },
        )

    @app.get("/about")
    def about():
        return render_template(
            "about.html",
            meta={
                "title": "About Us — AI Tool Marketplace",
                "description": "Learn about Aitoolhub and our mission to help you discover the best AI tools.",
                "path": url_for("about"),
            },
        )

    @app.get("/contact")
    def contact():
        return render_template(
            "contact.html",
            meta={
                "title": "Contact Us — AI Tool Marketplace",
                "description": "Contact Aitoolhub for tool suggestions, partnerships, bug reports, or general questions.",
                "path": url_for("contact"),
            },
        )

    @app.get("/health")
    def health():
        return jsonify({"ok": True})

    return app


def load_tools() -> list[dict]:
    if not TOOLS_PATH.exists():
        return []
    return json.loads(TOOLS_PATH.read_text(encoding="utf-8"))


def get_tool_by_slug(slug: str) -> dict | None:
    tools = load_tools()
    for tool in tools:
        if tool.get("slug") == slug:
            return tool
    return None


def apply_filters(tools: list[dict], q: str, category: str, pricing: str) -> list[dict]:
    q_norm = q.lower()

    def matches(tool: dict) -> bool:
        if category and tool.get("category") != category:
            return False
        if pricing and tool.get("pricing_type") != pricing:
            return False

        if not q_norm:
            return True

        haystack = " ".join(
            [
                str(tool.get("name", "")),
                str(tool.get("description", "")),
                " ".join(tool.get("use_cases", []) or []),
                " ".join(tool.get("tags", []) or []),
                str(tool.get("category", "")),
            ]
        ).lower()
        return q_norm in haystack

    return [t for t in tools if matches(t)]


def apply_sort(tools: list[dict], sort: str) -> list[dict]:
    sort = (sort or "").lower().strip()
    if sort not in SORT_OPTIONS:
        sort = "popularity"

    if sort == "new":
        return sorted(tools, key=lambda t: t.get("created_at", ""), reverse=True)
    if sort == "trending":
        return sorted(tools, key=lambda t: t.get("trending", 0), reverse=True)
    return sorted(tools, key=lambda t: t.get("popularity", 0), reverse=True)


def save_submission(payload: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    if SUBMISSIONS_PATH.exists():
        try:
            items = json.loads(SUBMISSIONS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []

    items.append(payload)
    SUBMISSIONS_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def send_submission_email(payload: dict) -> None:
    """Send email notification for new tool submission"""
    try:
        # Get Gmail app password from environment
        gmail_password = os.getenv("GMAIL_APP_PASSWORD")
        print(f"DEBUG: GMAIL_APP_PASSWORD loaded: {'Yes' if gmail_password else 'No'}")
        
        if not gmail_password:
            print("ERROR: GMAIL_APP_PASSWORD not set in environment variables")
            return
        
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = "noreply@aitoolhub.com"
        msg['To'] = "vasu934586@gmail.com"
        msg['Subject'] = "New AI submit from AI tool hub"
        
        # Email body
        body = f"""
New AI Tool Submission Details:

Tool Name: {payload.get('name', 'N/A')}
URL: {payload.get('url', 'N/A')}
Description: {payload.get('description', 'N/A')}
Category: {payload.get('category', 'N/A')}
Pricing: {payload.get('pricing_type', 'N/A')}
Submitter Email: {payload.get('email', 'Not provided')}
Submitted At: {payload.get('submitted_at', 'N/A')}

---
This is an automated notification from AI Tool Hub.
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        print("DEBUG: Attempting to connect to Gmail SMTP...")
        # Send email using Gmail SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        print("DEBUG: Connected to SMTP server")
        server.starttls()
        print("DEBUG: TLS started")
        server.login("vasu934586@gmail.com", gmail_password)
        print("DEBUG: Login successful")
        server.send_message(msg)
        print("DEBUG: Email sent successfully")
        server.quit()
        print("DEBUG: Connection closed")
        
    except Exception as e:
        # Log error but don't break the submission process
        print(f"ERROR: Failed to send email notification: {e}")
        import traceback
        print(f"ERROR: Traceback: {traceback.format_exc()}")


def recommend_with_keywords(task: str, tools: list[dict]) -> list[str]:
    task_norm = task.lower()
    tokens = set(re.findall(r"[a-z0-9]+", task_norm))

    def score(tool: dict) -> float:
        text = " ".join(
            [
                tool.get("name", ""),
                tool.get("description", ""),
                tool.get("category", ""),
                " ".join(tool.get("use_cases", []) or []),
                " ".join(tool.get("tags", []) or []),
            ]
        ).lower()
        words = set(re.findall(r"[a-z0-9]+", text))
        overlap = len(tokens.intersection(words))
        return overlap * 10 + float(tool.get("trending", 0)) + float(tool.get("popularity", 0)) * 0.01

    ranked = sorted(tools, key=score, reverse=True)
    return [t["slug"] for t in ranked[:5] if t.get("slug")]


def recommend_with_openai(task: str, tools: list[dict]) -> list[str] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    tool_catalog = [
        {
            "slug": t.get("slug"),
            "name": t.get("name"),
            "category": t.get("category"),
            "pricing_type": t.get("pricing_type"),
            "use_cases": t.get("use_cases", []),
            "tags": t.get("tags", []),
        }
        for t in tools
    ]

    prompt = (
        "You are an expert AI tools curator.\n"
        "Pick the best 3 to 5 tools for the user's task from the provided catalog.\n"
        "Return ONLY valid JSON with this shape: {\"slugs\": [\"tool-slug\", ...]}.\n"
        "No markdown, no extra keys.\n\n"
        f"User task: {task}\n\n"
        f"Catalog: {json.dumps(tool_catalog, ensure_ascii=False)}"
    )

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "Return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        slugs = parsed.get("slugs") or []
        slugs = [s for s in slugs if isinstance(s, str)]
        return slugs[:5]
    except Exception:
        return None


def recommend_with_gemini(task: str, tools: list[dict]) -> list[str] | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    tool_catalog = [
        {
            "slug": t.get("slug"),
            "name": t.get("name"),
            "category": t.get("category"),
            "pricing_type": t.get("pricing_type"),
            "use_cases": t.get("use_cases", []),
            "tags": t.get("tags", []),
        }
        for t in tools
    ]

    prompt = (
        "Pick the best 3 to 5 tools for the user's task from the provided catalog. "
        "Return ONLY valid JSON with this shape: {\"slugs\": [\"tool-slug\", ...]}. "
        "No markdown, no extra keys.\n\n"
        f"User task: {task}\n\n"
        f"Catalog: {json.dumps(tool_catalog, ensure_ascii=False)}"
    )

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt}],
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        slugs = parsed.get("slugs") or []
        slugs = [s for s in slugs if isinstance(s, str)]
        return slugs[:5]
    except Exception:
        return None


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
