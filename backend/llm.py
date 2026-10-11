import base64
from datetime import datetime, timezone, timedelta
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone
from core import db, LLM_KEY
from auth import require_user

SYSTEM = "You are a precise document layout analyser. Output only valid JSON."
PROVIDERS = {
    "emergent": {"label": "Emergent key (default)", "model": "gemini-3-flash-preview"},
    "gemini": {"label": "Google Gemini", "model": "gemini-3-flash-preview"},
    "openai": {"label": "OpenAI", "model": "gpt-5.6-terra"},
    "anthropic": {"label": "Anthropic Claude", "model": "claude-sonnet-5-5"},
    "openrouter": {"label": "OpenRouter", "model": "google/gemini-3-flash-preview", "base_url": "https://openrouter.ai/api/v1"},
    "compatible": {"label": "OpenAI-compatible server", "model": "", "base_url": "http://localhost:11434/v1"},
}
NATIVE = {"gemini", "openai", "anthropic"}
ai_api = APIRouter(prefix="/api/ai", dependencies=[Depends(require_user)])


async def ai_settings() -> dict:
    doc = await db.settings.find_one({"_id": "ai"}) or {}
    return {"provider": doc.get("provider", "emergent"), "models": doc.get("models", {}), "keys": doc.get("keys", {}),
            "base_url": doc.get("base_url", "")}


def resolve(st: dict) -> dict:
    """Active provider config; falls back to the Emergent key when the chosen provider has no key."""
    p = st["provider"]
    key = st["keys"].get(p)
    if p == "emergent" or (not key and p != "compatible"):
        return {"provider": "emergent", "model": PROVIDERS["emergent"]["model"], "key": LLM_KEY, "fallback": p != "emergent"}
    base = st["base_url"] if p == "compatible" else PROVIDERS[p].get("base_url")
    return {"provider": p, "model": st["models"].get(p) or PROVIDERS[p]["model"], "key": key or "none", "base_url": base, "fallback": False}


def _mime(b64: str) -> str:
    return "image/jpeg" if b64.startswith("/9j/") else "image/webp" if b64.startswith("UklG") else "image/png"


async def complete(cfg: dict, prompt: str, img_b64: str, session_id: str) -> str:
    if cfg["provider"] in NATIVE or cfg["provider"] == "emergent":
        vendor = "gemini" if cfg["provider"] == "emergent" else cfg["provider"]
        chat = LlmChat(api_key=cfg["key"], session_id=session_id, system_message=SYSTEM).with_model(vendor, cfg["model"])
        text, usage = "", None
        async for ev in chat.stream_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=img_b64)])):
            if isinstance(ev, TextDelta):
                text += ev.content
            elif isinstance(ev, StreamDone):
                usage = ev.usage
                break
        await record_usage(cfg, usage.input_tokens if usage else 0, usage.output_tokens if usage else 0)
        return text
    if not cfg["model"]:
        raise RuntimeError("No model name set for this provider")
    client = AsyncOpenAI(api_key=cfg["key"], base_url=cfg["base_url"], timeout=180)
    resp = await client.chat.completions.create(model=cfg["model"], messages=[
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [{"type": "text", "text": prompt},
                                     {"type": "image_url", "image_url": {"url": f"data:{_mime(img_b64)};base64,{img_b64}"}}]}])
    u = resp.usage
    await record_usage(cfg, u.prompt_tokens if u else 0, u.completion_tokens if u else 0)
    return resp.choices[0].message.content or ""


async def record_usage(cfg: dict, tin: int, tout: int):
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.ai_usage.update_one({"day": day, "provider": cfg["provider"], "model": cfg["model"]},
                                 {"$inc": {"calls": 1, "input_tokens": int(tin or 0), "output_tokens": int(tout or 0)}}, upsert=True)


def _mask(k: Optional[str]) -> Optional[str]:
    return f"••••{k[-4:]}" if k else None


@ai_api.get("/settings")
async def get_settings():
    st = await ai_settings()
    cfg = resolve(st)
    return {"provider": st["provider"], "models": st["models"], "base_url": st["base_url"],
            "keys": {p: _mask(st["keys"].get(p)) for p in PROVIDERS if p != "emergent"},
            "providers": {p: {"label": v["label"], "default_model": v["model"]} for p, v in PROVIDERS.items()},
            "active": {"provider": cfg["provider"], "model": cfg["model"], "fallback": cfg["fallback"]}}


class AiSettingsIn(BaseModel):
    provider: str
    model: Optional[str] = None
    key: Optional[str] = None  # only sent when changed; "" clears it
    base_url: Optional[str] = None


@ai_api.put("/settings")
async def save_settings(body: AiSettingsIn):
    if body.provider not in PROVIDERS:
        raise HTTPException(400, "Unknown AI provider")
    upd = {"provider": body.provider}
    if body.provider != "emergent":
        if body.model is not None:
            upd[f"models.{body.provider}"] = body.model.strip()
        if body.key is not None:
            upd[f"keys.{body.provider}"] = body.key.strip() or None
    if body.provider == "compatible":
        if body.base_url is not None and body.base_url.strip() and not body.base_url.strip().startswith(("http://", "https://")):
            raise HTTPException(400, "Server URL must start with http:// or https://")
        if body.base_url is not None:
            upd["base_url"] = body.base_url.strip()
    await db.settings.update_one({"_id": "ai"}, {"$set": upd}, upsert=True)
    return await get_settings()


def _sample_image() -> str:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (480, 160), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 470, 150], outline="black", width=3)
    d.text((30, 40), "QUESTION 1", fill="black")
    d.text((30, 80), "1.1  Solve for x: 2x + 3 = 11   (2)", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@ai_api.post("/test")
async def test_connection():
    cfg = resolve(await ai_settings())
    try:
        text = await complete(cfg, 'Read the image. Respond with ONLY JSON: {"ok": true, "first_label": "<the first sub-question number you see>"}',
                              _sample_image(), "ai-test")
    except Exception as e:
        raise HTTPException(400, f"{PROVIDERS[cfg['provider']]['label']} ({cfg['model']}) failed: {str(e)[:300]}")
    return {"ok": True, "provider": cfg["provider"], "model": cfg["model"], "fallback": cfg["fallback"], "reply": text[:300]}


# USD per 1M tokens (input, output). Rough list prices, edit in the app if they change.
DEFAULT_PRICES = {"gemini-3-flash-preview": [0.50, 3.00], "gemini-3.1-pro-preview": [2.00, 12.00], "gemini-2.5-flash": [0.30, 2.50],
                  "gemini-2.5-pro": [1.25, 10.00], "claude-sonnet-4-6": [3.00, 15.00], "claude-haiku-4-5-20251001": [1.00, 5.00],
                  "gpt-5.4-mini": [0.25, 2.00], "gpt-4.1": [2.00, 8.00], "gpt-4o-mini": [0.15, 0.60]}


async def prices() -> dict:
    custom = {d["_id"]: d["price"] for d in await db.ai_prices.find().to_list(500)}
    return {**DEFAULT_PRICES, **custom}


@ai_api.get("/usage")
async def usage(days: int = 30):
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)) - 1)).strftime("%Y-%m-%d")
    rows = await db.ai_usage.find({"day": {"$gte": since}}, {"_id": 0}).to_list(10000)
    table = await prices()
    by_model, by_day = {}, {}
    for r in rows:
        k = (r["provider"], r["model"])
        m = by_model.setdefault(k, {"provider": r["provider"], "model": r["model"], "calls": 0, "input_tokens": 0, "output_tokens": 0})
        for f in ("calls", "input_tokens", "output_tokens"):
            m[f] += r.get(f, 0)
        by_day[r["day"]] = by_day.get(r["day"], 0) + r.get("calls", 0)
    total = 0.0
    for m in by_model.values():
        p = table.get(m["model"])
        m["price"] = p
        m["cost"] = round(m["input_tokens"] / 1e6 * p[0] + m["output_tokens"] / 1e6 * p[1], 4) if p else None
        m["paid_by"] = "Emergent credits" if m["provider"] == "emergent" else "your own key"
        total += m["cost"] or 0
    return {"days": days, "models": sorted(by_model.values(), key=lambda m: -m["calls"]), "total_cost": round(total, 4),
            "total_calls": sum(m["calls"] for m in by_model.values()), "daily": [{"day": d, "calls": by_day[d]} for d in sorted(by_day)]}


class PriceIn(BaseModel):
    model: str
    input: float
    output: float


@ai_api.put("/prices")
async def set_price(body: PriceIn):
    if body.input < 0 or body.output < 0 or not body.model.strip():
        raise HTTPException(400, "Prices must be zero or more")
    await db.ai_prices.update_one({"_id": body.model.strip()}, {"$set": {"price": [body.input, body.output]}}, upsert=True)
    return await usage()
