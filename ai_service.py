"""
AI Service — Gemini 2.5 Flash integration for intelligent APK verification.
Provides fallback to pattern-based matching when API key is not available.
"""

import re
import json
from typing import Optional

# ── Gemini SDK (optional) ──

HAS_GEMINI = False
try:
    from google import genai
    HAS_GEMINI = True
except ImportError:
    try:
        import google.generativeai as genai_old
        HAS_GEMINI = True
    except ImportError:
        pass

# ── Known versions cache (auto-updated by AI) ──
# Maps package_name -> {"versionName": "...", "versionCode": "...", "source": "ai|cached"}
_KNOWN_VERSIONS = {}

# ── Samsung version patterns ──
# Common patterns in Samsung version strings
_VERSION_PATTERNS = [
    (r'(\d+\.\d+\.\d+\.\d+)', lambda m: m.group(1)),
    (r'(\d+\.\d+\.\d+)', lambda m: m.group(1)),
    (r'v?(\d+\.\d+)', lambda m: m.group(1)),
    (r'(\d{4,6})', lambda m: m.group(1)),  # fallback: numeric codes
]


def get_api_key() -> Optional[str]:
    """Get Gemini API key from environment variable."""
    import os
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def is_available() -> bool:
    """Check if Gemini AI is available (SDK + API key)."""
    return HAS_GEMINI and bool(get_api_key())


def _call_gemini(prompt: str, system: str = "") -> Optional[str]:
    """Call Gemini 2.5 Flash and return text response."""
    api_key = get_api_key()
    if not api_key or not HAS_GEMINI:
        return None

    try:
        if HAS_GEMINI:
            # Try new SDK first
            try:
                client = genai.Client(api_key=api_key)
                model = client.models.get(model="gemini-2.5-flash")
                contents = [prompt]
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config={
                        "temperature": 0.2,
                        "max_output_tokens": 500,
                    }
                )
                return response.text
            except AttributeError:
                # Fall back to old SDK
                import google.generativeai as genai_old
                genai_old.configure(api_key=api_key)
                model = genai_old.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    generation_config={
                        "temperature": 0.2,
                        "max_output_tokens": 500,
                    }
                )
                response = model.generate_content(prompt)
                return response.text
    except Exception as exc:
        print(f"[AI] Gemini call failed: {exc}")
        return None


# ═══════════════════════════════════════════════
#  PUBLIC API FUNCTIONS
# ═══════════════════════════════════════════════


def verify_latest_version(package: str, current_version: str,
                          current_code: str, app_name: str = "") -> dict:
    """
    Use AI to verify if the found version is the latest.
    Returns dict with: is_latest, latest_version, notes, source
    """
    result = {
        "is_latest": True,
        "latest_version": current_version,
        "latest_code": current_code,
        "notes": "",
        "source": "galaxy_store",
        "verified": False,
    }

    if not is_available():
        result["notes"] = "IA non disponible (clé API manquante)"
        result["verified"] = False
        return result

    prompt = f"""Tu es un expert des applications Samsung Galaxy Store.

Application: {app_name or package}
Package: {package}
Version trouvée: {current_version} (code: {current_code})

Questions:
1. Est-ce la dernière version connue de cette application Samsung ?
2. Si non, quelle est la dernière version ?
3. Y a-t-il des informations supplémentaires importantes ?

Réponds UNIQUEMENT en JSON formaté comme ceci :
{{
  "is_latest": true/false,
  "latest_version": "version ou null si identique",
  "latest_code": "code ou null",
  "notes": "brève explication",
  "confidence": "high/medium/low"
}}
"""

    response = _call_gemini(prompt)
    if not response:
        result["notes"] = "Pas de réponse de l'IA"
        return result

    # Parse JSON from response
    try:
        # Find JSON block
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            result["is_latest"] = data.get("is_latest", True)
            result["latest_version"] = data.get("latest_version") or current_version
            result["latest_code"] = data.get("latest_code") or current_code
            result["notes"] = data.get("notes", "")
            result["confidence"] = data.get("confidence", "low")
            result["source"] = "ai"
            result["verified"] = True

            # Cache the result
            _KNOWN_VERSIONS[package] = {
                "versionName": result["latest_version"],
                "versionCode": result["latest_code"],
                "source": "ai",
            }
    except (json.JSONDecodeError, AttributeError) as exc:
        result["notes"] = f"Erreur de parsing: {exc}"
        result["verified"] = False

    return result


def ai_search(query: str) -> list:
    """
    Natural language search for Samsung apps using AI.
    Example: "find the clock app" → com.samsung.android.app.clock
    Falls back to keyword matching if AI is unavailable.
    """
    if not is_available():
        return []  # Caller should fall back to regular search

    prompt = f"""Tu es un expert des applications Samsung Galaxy Store.

Un utilisateur cherche une application Samsung avec cette requête: "{query}"

Trouve les applications Samsung officielles correspondantes.
Réponds UNIQUEMENT en JSON - une liste d'objets:
[
  {{
    "package": "com.samsung.android.app.notes",
    "name": "Samsung Notes",
    "category": "Productivity",
    "confidence": "high/medium/low",
    "reason": "pourquoi cette correspondance"
  }}
]

Limite à 5 résultats maximum. Si rien ne correspond, réponds [].
"""

    response = _call_gemini(prompt)
    if not response:
        return []

    try:
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except (json.JSONDecodeError, AttributeError):
        pass

    return []


def analyze_package_name(description: str) -> Optional[str]:
    """
    Use AI to figure out a package name from a natural language description.
    Example: "the one that controls the edge screen" → com.samsung.android.iceview
    """
    if not is_available():
        return None

    prompt = f"""Quel est le package name Android de l'application Samsung décrite ci-dessous ?
Réponds UNIQUEMENT par le package name, rien d'autre.

Description: {description}

Package:"""

    response = _call_gemini(prompt)
    if response:
        response = response.strip().strip('"').strip("'")
        # Basic validation: must look like a package name
        if re.match(r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$', response):
            return response

    return None


def batch_verify(packages: list) -> list:
    """
    Batch verify multiple packages in one AI call.
    packages: list of dicts with keys: package, name, versionName, versionCode
    Returns enriched versions list.
    """
    if not is_available() or not packages:
        return packages

    # Limit to avoid token overflow
    batch = packages[:15]
    pkgs_str = "\n".join([
        f"- {p.get('name', p['package'])} ({p['package']}) → v{p.get('versionName', '?')}"
        for p in batch
    ])

    prompt = f"""Voici une liste d'applications Samsung trouvées via le Galaxy Store API.
Pour chacune, dis-moi si c'est probablement la dernière version ou s'il y a plus récent.

{pkgs_str}

Réponds UNIQUEMENT en JSON:
[
  {{
    "package": "com.samsung.android...",
    "is_latest": true/false,
    "suggested_version": "version si différente ou null",
    "notes": "info brève"
  }}
]
"""
    response = _call_gemini(prompt)
    if not response:
        return packages

    try:
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if json_match:
            updates = json.loads(json_match.group())
            updates_map = {u["package"]: u for u in updates}

            enriched = []
            for pkg in packages:
                p = dict(pkg)
                if p["package"] in updates_map:
                    u = updates_map[p["package"]]
                    p["ai_verified"] = u.get("is_latest", True)
                    p["ai_notes"] = u.get("notes", "")
                    if not u.get("is_latest") and u.get("suggested_version"):
                        p["ai_suggested"] = u["suggested_version"]
                enriched.append(p)
            return enriched
    except (json.JSONDecodeError, AttributeError):
        pass

    return packages


def system_check() -> dict:
    """Check if AI system is ready."""
    return {
        "available": is_available(),
        "sdk_installed": HAS_GEMINI,
        "has_api_key": bool(get_api_key()),
        "cached_versions": len(_KNOWN_VERSIONS),
    }
