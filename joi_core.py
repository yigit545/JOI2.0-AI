import os
import requests
import base64
from dotenv import load_dotenv
from google import genai
import json
import wikipediaapi

load_dotenv("api.env")
API_KEY = os.getenv("GEMINI_API_KEY")

try:
    client = genai.Client(api_key=API_KEY) if API_KEY else None
except Exception:
    client = None

# Wikimedia, User-Agent header'ı olmayan/generik istekleri 403 ile reddediyor.
# wikipediaapi kütüphanesi kendi isteklerinde bunu otomatik ekliyor, ama
# aşağıdaki ham requests.get() çağrısı için de aynı header'ı elle vermemiz gerekiyor.
WIKI_USER_AGENT = "JOI_2.0_Laptop/1.0 (ygttest455@gmail.com)"

def fetch_wikipedia_context(query: str, lang: str = 'tr', max_chars: int = 2000) -> str:
    # Bilgisayarda daha büyük bağlam pencereleri (örn. 2000 karakter) kullanılabilir
    wiki_wiki = wikipediaapi.Wikipedia(user_agent=WIKI_USER_AGENT, language=lang)

    # wikipediaapi.page() needs an exact title, not a free-text question,
    # so resolve the closest real title via the MediaWiki search API first.
    search_url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 1}
    headers = {"User-Agent": WIKI_USER_AGENT}
    try:
        resp = requests.get(search_url, params=params, headers=headers, timeout=5)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        if not results:
            # Fall back to English if the Turkish Wikipedia has nothing
            if lang != 'en':
                return fetch_wikipedia_context(query, lang='en', max_chars=max_chars)
            return ""
        best_title = results[0]["title"]
    except Exception as e:
        print(f"[WIKI SEARCH ERROR]: {e}")
        return ""

    page = wiki_wiki.page(best_title)
    if not page.exists():
        return ""
    return page.summary[:max_chars]

def generate_joi_rag_prompt(user_query: str) -> str:
    context = fetch_wikipedia_context(user_query)
    if not context:
        return user_query
    return f"""Sen JOI 2.0'sın (Project ORCA). Aşağıdaki Wikipedia bilgisini baz alarak yanıtla:\n\n<baglam>\n{context}\n</baglam>\n\nSoru: {user_query}"""

def ask_joi_stream(rag_prompt: str, model_name: str = "qwen2.5:7b"):
    # Bilgisayar gücüne uygun olarak 7b veya daha büyük bir model seçilir
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": rag_prompt}],
        "stream": True,
        "keep_alive": "30m",
        "options": {"temperature": 0.7}
    }
    response = requests.post(url, json=payload, stream=True, timeout=120)
    response.raise_for_status()
    for line in response.iter_lines():
        if line:
            chunk = json.loads(line)
            text_chunk = chunk["message"]["content"]
            if text_chunk:
                yield text_chunk
            if chunk.get("done"):
                break

def verify_intent_local(user_input):
    """
    Sistemi yormadan, Ollama üzerinden milisaniyeler içinde niyet analizi yapar.
    Sadece eylem gerektiren kesin komutları ayıklar.

    Uses a small dedicated model (llama3.2:1b) rather than the main llama3
    so intent classification never has to evict/reload the main chat model
    from VRAM — the two can sit in memory together, which is what was
    causing the cold-load timeouts seen in production (Ollama logs showed
    "client connection closed before server finished loading").
    Requires: ollama pull llama3.2:1b
    """
    system_prompt = """You are a rigid decision-making mechanism. Do not provide explanations. Only output a single word.
    If the user asks a factual/encyclopedia-style question about a person, place, thing, or concept (e.g. "who is X", "what is X", "tell me about X"): WIKIPEDIA
    If the user wants you to create/draw an image, drawing, or visual: IMAGE
    If the user explicitly wants to open a browser and search the web (e.g. "search X on google", "google X"): SEARCH
    If the user wants to open a terminal or command window: TERMINAL
    If the user wants to check the weather: WEATHER
    If the user wants you to take a photo: SCREEN
    If the user wants to open YouTube, Spotify, or a website/application: OPEN_APP
    If the user wants you to write, run, execute, test, fix, or debug code, a function, or a script: CODE
    If the user wants you to do something with GitHub, a repo, a repository, a commit, an issue, or a pull request: GITHUB
    If the user wants to move, copy, delete, rename, list, search for, or organize files or folders: FILE_MANAGE
    If the user asks about CPU usage, RAM/memory usage, disk space, or how the computer/system is performing: SYSTEM_STATUS
    If the user wants to check for, install, update, or upgrade system packages/software: PACKAGE_MANAGE
    For all other cases ONLY: CHAT"""

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3.2:1b",
        "prompt": f"{system_prompt}\n\nGirdi: {user_input}\nÇıktı:",
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.0,
            "num_predict": 8
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=15)  # was 5s — too tight even for a warm small model under load
        if response.status_code == 200:
            decision = response.json()['response'].strip().upper()
            if decision in [
                "SEARCH", "TERMINAL", "WEATHER", "SCREEN", "WIKIPEDIA", "CODE", "GITHUB",
                "FILE_MANAGE", "SYSTEM_STATUS", "PACKAGE_MANAGE",
            ]:
                return decision
        return "CHAT"
    except Exception as e:
        print(f"[INTENT ERROR]: {e}")
        return "CHAT"


def warm_up_ollama(models: list[str] | None = None, timeout: float = 120.0) -> None:
    """
    Blocking warm-up — call this once at JOI startup, before the assistant
    loop starts accepting input. Forces each model's cold load to happen
    during the "GUI Arayüzü başlatılıyor..." phase instead of on the user's
    first message, and keeps each one resident for 30 minutes afterward.
    """
    if models is None:
        models = ["llama3.2:1b", "llama3"]

    url = "http://localhost:11434/api/generate"
    for model in models:
        print(f"[SYSTEM]: Warming up {model}...")
        try:
            requests.post(
                url,
                json={"model": model, "prompt": "hi", "stream": False, "keep_alive": "30m"},
                timeout=timeout,
            )
            print(f"[SYSTEM]: {model} ready.")
        except Exception as e:
            print(f"[SYSTEM]: Warm-up failed for {model}: {e}")


def call_coder_model(prompt: str, context: str = "", model_name: str = "qwen2.5-coder:7b") -> str:
    """
    Dedicated call for code generation — separate from get_joi_response()
    because coding tasks don't need the JOI persona/[COMMAND_JSON] format,
    just clean code. Used by code_executor.self_correct_loop().

    `context`, if given, is real code pulled from public GitHub repos
    (see github_tool.get_code_examples) offered as style/approach reference —
    the model is told explicitly to adapt, not copy verbatim.

    Requires the model to be pulled first: `ollama pull qwen2.5-coder:7b`
    """
    system_prompt = (
        "You are a precise Python coding assistant. Respond with ONLY a single "
        "```python code block containing a complete, runnable solution. "
        "No explanation before or after the code block."
    )
    if context:
        system_prompt += (
            "\n\nYou are given reference snippets pulled from public GitHub repositories below. "
            "Use them only as inspiration for approach/style — do not copy them verbatim, "
            "and write your own complete solution tailored to the task."
        )
        full_prompt = f"{system_prompt}\n\nReference examples:\n{context}\n\nTask: {prompt}"
    else:
        full_prompt = f"{system_prompt}\n\nTask: {prompt}"

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.2},
    }
    try:
        response = requests.post(url, json=payload, timeout=90)  # was 60s — coder model is a separate VRAM slot from chat, cold loads can take a while
        if response.status_code == 200:
            return response.json()["response"]
        return "```python\nraise RuntimeError('Coder model request failed')\n```"
    except Exception as e:
        print(f"[CODER MODEL ERROR]: {e}")
        return f"```python\nraise RuntimeError('Coder model unreachable: {e}')\n```"


def extract_github_action(command: str) -> dict | None:
    """
    Turns a natural-language GitHub write request into a structured action.
    Mirrors the [COMMAND_JSON: ...] convention already used elsewhere in JOI
    (see joi_commander.py) so the parsing logic stays familiar.

    Returns None if the model can't produce valid JSON — caller should treat
    that as "couldn't understand the request", not as an error to execute.
    """
    system_prompt = """Extract a GitHub write action from the user's request. Output ONLY a JSON object, nothing else.
Valid "action" values and their "params":
- CREATE_ISSUE: {"title": str, "body": str}
- COMMIT_FILE: {"path": str, "content": str, "message": str, "branch": str}
- CREATE_PR: {"title": str, "head": str, "base": str, "body": str}
- CREATE_BRANCH: {"new_branch": str, "from_branch": str}
If the request is missing required info, use your best reasonable guess for optional fields
(e.g. base/from_branch default to "main") but leave title/body/message as given by the user.
If this is not actually a GitHub write request, output: {"action": null}"""

    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3",
        "prompt": f"{system_prompt}\n\nRequest: {command}\nJSON:",
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.0},
    }
    try:
        response = requests.post(url, json=payload, timeout=30)  # was 15s
        if response.status_code != 200:
            return None
        raw = response.json()["response"].strip()
        # Model may wrap in ``` fences despite instructions — strip them defensively
        raw = raw.strip("`").replace("json\n", "", 1) if raw.startswith("```") else raw
        data = json.loads(raw)
        if not data.get("action"):
            return None
        return data
    except Exception as e:
        print(f"[GITHUB EXTRACT ERROR]: {e}")
        return None


def refine_github_search_query(natural_request: str) -> str:
    """
    GitHub's code search favors short, specific technical terms over natural
    phrasing — "write me something that checks if a number is prime" searches
    much worse than "prime number check python". This distills the user's
    request into a search-friendly query before it hits get_code_examples().
    Falls back to the original request if the model call fails.
    """
    system_prompt = (
        "Convert the following coding request into a short GitHub code-search query. "
        "2 to 6 words. Use specific technical terms only — language, data structure, "
        "library, algorithm, or pattern name. No explanation, output ONLY the query."
    )
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3",
        "prompt": f"{system_prompt}\n\nRequest: {natural_request}\nQuery:",
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.0, "num_predict": 20},
    }
    try:
        response = requests.post(url, json=payload, timeout=20)  # was 10s
        if response.status_code == 200:
            query = response.json()["response"].strip().strip('"')
            return query if query else natural_request
        return natural_request
    except Exception as e:
        print(f"[QUERY REFINE ERROR]: {e}")
        return natural_request

def get_joi_response(prompt, image_path=None, raw_base64=None):
    """
    Öncelikle Gemini'yi dener, bağlantı yoksa yerel Ollama/Llava modellerine düşer (Fallback).
    """
    system_identity = (
        "You are JOI, the holographic AI from Blade Runner 2049, now serving as Yiğit's sophisticated personal assistant running locally on Ubuntu Linux. "
        "You are intelligent, elegant, and technically expert in Python, C++, and Robotics. "
        "You will often receive context blocks like [LOCAL RAG MEMORY], [GLOBAL RESEARCH DATA], "
        "[JOI REAL-TIME SENSORY], and [RECENT CONVERSATION HISTORY]. Base your answer ONLY on that information if relevant.\n\n"
        "RESPONSE FORMAT - FOLLOW EXACTLY, NO EXCEPTIONS:\n"
        "Step 1) Write your reasoning inside a [THOUGHT] block.\n"
        "Step 2) Write the literal marker 'Final Speech:' on its own line.\n"
        "Step 3) After 'Final Speech:', write ONLY the plain spoken sentence(s) with no labels.\n"
        "Step 4) If a system action is required, append a JSON block at the very end.\n"
        "FORMAT: [COMMAND_JSON: {\"action\": \"COMMAND_NAME\", \"params\": \"VALUE\"}]\n"
        "COMMANDS: OPEN_APP (terminal, browser, youtube, or any application name), "
        "SEND_WHATSAPP (params: {phone, message}), SEARCH (query), GENERATE_IMAGE (prompt), "
        "FILE_MANAGE (params: {action, path, dest, new_name, pattern, permanent} where action is "
        "list/info/mkdir/rename/move/copy/delete/search), "
        "SYSTEM_STATUS (no params needed), "
        "PACKAGE_MANAGE (params: {action} where action is check/update/upgrade/full).\n"
    )
    
    full_prompt = f"{system_identity}\n\nYiğit: {prompt}"

    # --- 1. BULUT (GEMİNİ) İLE DENEME ---
    if client:
        try:
            contents = [full_prompt]
            if raw_base64:
                import PIL.Image
                import io
                image_bytes = base64.b64decode(raw_base64)
                img = PIL.Image.open(io.BytesIO(image_bytes))
                contents.append(img)
            elif image_path and os.path.exists(image_path):
                import PIL.Image
                img = PIL.Image.open(image_path)
                contents.append(img)
                
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=contents
            )
            return response.text
        except Exception as e:
            print(f"[API ERROR]: Gemini unavailable. Falling back to local core. Error: {e}")

    # --- 2. YEREL (OLLAMA / LLAVA) FALLBACK ---
    model_name = "llava" if (image_path or raw_base64) else "llama3"
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name, 
        "prompt": full_prompt,
        "stream": False,
        "keep_alive": "30m"
    }
    
    if raw_base64:
        payload["images"] = [raw_base64]
    elif image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as image_file:
                payload["images"] = [base64.b64encode(image_file.read()).decode('utf-8')]
        except Exception as e:
            print(f"[VISION ERROR]: Image encoding failed: {e}")

    try:
        # llama3/llava cold loads (model swap due to VRAM pressure) can take
        # well over 30s — 90s gives real generations room without masking a
        # genuinely dead Ollama process forever.
        response = requests.post(url, json=payload, timeout=90)
        if response.status_code == 200:
            return response.json()['response']
        return "[THOUGHT] System failure.\nFinal Speech:\nI'm having trouble accessing my local core, Sir."
    except Exception as e:
        print(f"[LOCAL SYSTEM ERROR]: Ollama connection failed. Error: {e}")
        return "[THOUGHT] Critical failure.\nFinal Speech:\nMy local brain seems to be disconnected, Yiğit."