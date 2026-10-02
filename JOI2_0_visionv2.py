import os
import re
from datetime import datetime
import subprocess
from PIL import ImageGrab
import queue
import io
import re
import webbrowser
import cv2
import time
import multiprocessing
import threading
import sys
from pyscreeze import screenshot
import requests
import json
import base64
from JOI2_0_system_control import JOIControl
from JOI2_0_face_animation import JOIFace
try:
    from ddgs import DDGS  # yeni paket adı
except ImportError:
    from duckduckgo_search import DDGS  # eski paket adı (deprecated ama hâlâ çalışıyor)
from pynput import keyboard
import argparse
from JOI2_0_memory import JOIMemory
from joi_commander import JOICommander
from ultralytics import YOLO  # Gerçek zamanlı nesne tanıma için eklendi
from joi_core import verify_intent_local, generate_joi_rag_prompt, ask_joi_stream, fetch_wikipedia_context, call_coder_model, extract_github_action, refine_github_search_query
from joi_image_gen import generate_and_show_image
from code_executor import self_correct_loop
from github_tool import GitHubTool

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

# %100 Yerel mimari için Hafıza Yönetimi başlatılıyor
joi_memory = JOIMemory()

# Gerçek zamanlı nesne tanıma için hafif YOLO modeli yükleniyor
try:
    yolo_model = YOLO("yolov8n.pt")
except Exception as e:
    print(f"[YOLO INITIALIZE ERROR]: Could not load YOLO. Object detection disabled: {e}")
    yolo_model = None

def get_joi_response(prompt, image_path=None, raw_base64=None):
    """
    Doğrudan yerel Ollama modeline istek gönderir.
    Görsel varsa 'llava' (görme beyni), sadece metin varsa 'llama3' kullanılır.
    """
    model_name = "llava" if (image_path or raw_base64) else "llama3"
    
    system_identity = (
        "You are JOI, Yiğit's sophisticated AI companion running locally on UbuntuLinux. "
        "You can also tell your opinion about the topic and make a little commentary."
        "You will often receive context blocks like [LOCAL RAG MEMORY], [GLOBAL RESEARCH DATA], "
        "[JOI REAL-TIME SENSORY], and [RECENT CONVERSATION HISTORY]. If the answer is present in "
        "one of these, base your answer ONLY on that information. If it is not present, say so "
        "honestly instead of guessing or inventing facts.\n\n"
        "RESPONSE FORMAT - FOLLOW EXACTLY, NO EXCEPTIONS:\n"
        "Step 1) Write your reasoning inside a [THOUGHT] block.\n"
        "Step 2) Write the literal marker 'Final Speech:' on its own line.\n"
        "Step 3) After 'Final Speech:', write ONLY the plain spoken sentence(s) with no labels, "
        "no headers, no brackets, no markdown - just the words JOI would say out loud.\n"
        "Step 4) If (and only if) a system action is required, append a JSON block at the very end.\n"
        "FORMAT: [COMMAND_JSON: {\"action\": \"COMMAND_NAME\", \"params\": \"VALUE\"}]\n"
        "COMMANDS: OPEN_APP (terminal, browser), SEND_WHATSAPP (params: {phone, message}), SEARCH (query).\n\n"
        "NEVER invent your own headers such as '[System Response]' or '[CLEAR SPEECH]' - the ONLY "
        "allowed markers are [THOUGHT], 'Final Speech:', and [COMMAND_JSON: ...].\n"
    )
    
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name, 
        "prompt": f"{system_identity}\n\n{prompt}",
        "stream": False
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
        response = requests.post(url, json=payload, timeout=25) 
        if response.status_code == 200:
            return response.json()['response']
        return "I'm having trouble accessing my local core, Sir."
    except Exception as e:
        print(f"[LOCAL SYSTEM ERROR]: Ollama connection failed. Error: {e}")
        return "My local brain seems to be disconnected, Yiğit."

def clean_response(raw_text):
    """
    Modelin ürettiği ham metni kullanıcıya gösterilecek/söylenecek temiz konuşmaya çevirir.
    Model bazen [THOUGHT], Final Speech:, [System Response], [CLEAR SPEECH] gibi
    farklı başlıklar üretebiliyor - bu fonksiyon hepsini tek yerde, sağlam biçimde temizler.
    """
    if not raw_text:
        return ""

    # 1. [COMMAND_JSON: ...] bloğunu tamamen çıkar (konuşmaya karışmasın)
    text = raw_text.split("[COMMAND_JSON")[0]

    if "Final Speech:" in text:
        # En güvenilir durum: model istenen formatı doğru izlemiş
        text = text.split("Final Speech:")[-1]
    else:
        # Model formatı izlemedi (ör. [System Response] / [CLEAR SPEECH] gibi kendi
        # başlığını uydurdu). Bu durumlarda gerçek cevap neredeyse her zaman EN SON
        # paragrafta oluyor; önceki paragraf(lar) THOUGHT/analiz kısmı oluyor.
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        if len(paragraphs) > 1:
            text = paragraphs[-1]
        # tek paragrafsa elimizdeki tek şey odur, olduğu gibi devam edilir

    # 2. Satır başındaki herhangi bir "[BAŞLIK]" veya "Başlık:" etiketini kaldır
    #    Örn: "[System Response]", "[CLEAR SPEECH]", "JOI:", "Output:"
    text = re.sub(r'^\s*\[[A-Za-z0-9 _\-]+\]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[A-Za-z ]{2,20}:\s*(?=\S)', '', text, flags=re.MULTILINE)

    # 3. Kalan tek başına köşeli parantez satırlarını / boş satırları temizle
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln and not re.fullmatch(r'\[[^\]]*\]', ln)]
    text = " ".join(lines)

    return text.strip()

def tts_consumer_loop(user_query: str):
    sentence_delimiters = re.compile(r'([.!?\n])')
    buffer = ""
    
    print(f"Kullanıcı: {user_query}")
    print("JOI 2.0: ", end="", flush=True)
    
    rag_prompt = generate_joi_rag_prompt(user_query)
    
    for chunk in ask_joi_stream(rag_prompt):
        buffer += chunk
        match = sentence_delimiters.search(buffer)
        if match:
            split_index = match.end()
            sentence = buffer[:split_index].strip()
            if sentence:
                print(sentence, end=" ", flush=True)
                # Bilgisayarındaki TTS motorunu (örn. edge-tts veya pyttsx3) 
                # ve Flet/CustomTkinter yüz animasyonunu burada tetikleyebilirsin:
                # play_audio_and_animate(sentence)
                
            buffer = buffer[split_index:]
            
    if buffer.strip():
        print(buffer.strip(), flush=True)
        # play_audio_and_animate(buffer.strip())

def get_weather(city="Sakarya"):
    try:
        url = f"https://wttr.in/{city}?format=%C+%t&lang=en"
        response = requests.get(url, timeout=5)
        return response.text.strip()
    except:
        return "Weather information is currently unavailable."

def internet_search(query):
    try:
        results_text = ""
        with DDGS() as ddgs:
            search_query = f"{query} detailed information"
            results = list(ddgs.text(search_query, max_results=3)) 
            
            if results:
                results_text = "\n[GLOBAL RESEARCH DATA]:\n"
                for r in results:
                    results_text += f"- Source: {r['title']} | Content: {r['body']}\n"
                return results_text
            return "\n[SYSTEM: No global sources found for this query.]"
    except Exception as e:
        return f"\n[SYSTEM: Search engine error: {e}]"

def run_hologram(speaking_event, status_val, trigger_event, text_queue):
    face = JOIFace(status_val, speaking_event, trigger_event, text_queue)
    def sync():
        face.is_speaking = speaking_event.is_set()
        face.status = status_val.value
        face.root.after(100, sync)
    face.root.after(100, sync)
    face.start()

class JOIEye:
    def __init__(self, speaking_event, status_val, trigger_event, text_queue, skip_greeting=False, quiet=False, response_queue=None,skip_vision=False):
        self.skip_vision = skip_vision
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.current_frame = None
        
        if not self.skip_vision:
            self.cap = cv2.VideoCapture(0)
        else:
            self.cap = None

        self.joi_hand = JOIControl()

        # GitHub bağlantısı isteğe bağlıdır — GITHUB_TOKEN yoksa JOI yine de
        # normal şekilde başlar, sadece GITHUB niyeti devre dışı kalır.
        try:
            self.github_tool = GitHubTool()
            self.github_owner = os.environ.get("GITHUB_DEFAULT_OWNER")
            self.github_repo = os.environ.get("GITHUB_DEFAULT_REPO")
        except Exception as e:
            print(f"[GITHUB WARN]: GitHub tool disabled — {e}")
            self.github_tool = None
            self.github_owner = None
            self.github_repo = None

        self.pending_action = None  # onay bekleyen GitHub yazma eylemi (varsa)

        self.speaking_event = speaking_event
        self.status_val = status_val
        self.trigger_event = trigger_event
        self.text_queue = text_queue
        self.response_queue = response_queue  # GUI/TUI'ye cevap metnini akıtmak için
        self.has_greeted = False
        self.skip_greeting = skip_greeting
        self.quiet = quiet
        self.vision_active = not skip_vision  # Görsel inceleme aktif mi?

        # Hafıza ve Sürekli Görme Değişkenleri
        self.conversation_history = []
        self.max_history_len = 5
        self.current_live_vision_context = "Scanning environment..."
        self.detected_objects_list = [] # Canlı algılanan anlık nesneler
        
        self.listener = keyboard.Listener(on_press=self.on_press)
        self.listener.start()
        self.commands = {
            "/listen": self.cmd_listen,
            "/weather": self.cmd_weather,
            "/terminal": self.cmd_terminal,
            "/update": self.cmd_update,
            "/upgrade": self.cmd_upgrade,
            "/clear": self.cmd_clear_screen,
            "/help": self.cmd_help,
            "/search": self.cmd_search,
            "/web": self.cmd_web,
            "/youtube": self.cmd_youtube,
            "/music": self.cmd_music,
            "/goodnight": self.cmd_goodnight,
            "/learn": self.cmd_learn,
            "/blind": self.cmd_stop_vision,
            "/see": self.cmd_start_vision,
            "/screen": self.cmd_capture_screen,
            "/code": self.cmd_code,
            "/github": self.cmd_github,
        }
    
    def cmd_capture_screen(self, args=None):
        """Terminal penceresini gizleyerek bilgisayarın ekran görüntüsünü alır ve Llava modeline gönderir."""
        from PIL import ImageGrab
        import subprocess
        
        self.status_val.value = "processing"
        print("\n[SCREENSHOT]: Capturing background display (hiding terminal)...")
        self.joi_hand.speak("Hiding my terminal and looking at your background, Yiğit.", quiet=self.quiet)
        
        active_window_id = None
        try:
            # 1. O an aktif olan terminal penceresinin ID'sini yakala
            active_window_id = subprocess.check_output(["xdotool", "getactivewindow"]).decode().strip()
            # 2. Terminal penceresini simge durumuna küçült (Gizle)
            subprocess.call(["xdotool", "windowminimize", active_window_id])
            # Pencerenin kapanma animasyonu için çok kısa bir an bekle (Milisaniyeler)
            time.sleep(0.3)
        except Exception as win_err:
            print(f"[WINDOW CONTROL WARN]: Could not hide terminal window: {win_err}")
        
        try:
            # 3. Terminal gizlendikten sonra arkadaki ekranı yakala
            screenshot = ImageGrab.grab()
            screen_path = "joi_screen_snap.jpg"
            img_buffer = io.BytesIO()
            screenshot.save(img_buffer, format="JPEG", quality=80)
            base64_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
            # --- Terminali Geri Getirme İşlemi ---
            # Fotoğraf çekildiği an kullanıcının beklememesi için terminali hemen geri açıyoruz
            if active_window_id:
                try:
                    subprocess.call(["xdotool", "windowactivate", active_window_id])
                except: pass
            # -------------------------------------
            
            user_prompt = args if args else "Analyze this screenshot in detail. What is on the screen? Explain briefly."
            
            print("[VISION ANALYZING]: JOI is processing the screenshot...")
            ai_response = get_joi_response(user_prompt, raw_base64=base64_str)

            # Yanıt temizleme mekanizması (merkezi fonksiyon)
            clean_speech = clean_response(ai_response)
            
            print(f"JOI: {clean_speech}")
            self.joi_hand.speak(clean_speech, quiet=self.quiet)
            if self.response_queue is not None and clean_speech:
                self.response_queue.put(clean_speech)
            
            if os.path.exists(screen_path):
                os.remove(screen_path)
                
        except Exception as e:
            print(f"[SCREENSHOT ERROR]: Failed to analyze screen: {e}")
            self.joi_hand.speak("I couldn't grab your screen right now, Sir.", quiet=self.quiet)
            # Hata oluşsa bile terminalin kapalı kalmaması için güvenlik önlemi
            if active_window_id:
                try: subprocess.call(["xdotool", "windowactivate", active_window_id])
                except: pass
            
        self.status_val.value = "idle"

    def cmd_stop_vision(self, args=None):
        """JOI'nin arka plandaki görsel inceleme ve Llava analizini durdurur."""
        self.vision_active = False
        self.detected_objects_list = []
        self.current_live_vision_context = "Vision paused by user."
        print("[VISION]: Semantic eye tracking and object detection paused.")
        self.joi_hand.speak("I've closed my eyes and paused environment analysis, Yiğit.", quiet=self.quiet)

    def cmd_start_vision(self, args=None):
        """Görsel incelemeyi yeniden başlatır."""
        self.vision_active = True
        print("[VISION]: Semantic eye tracking reactivated.")
        self.joi_hand.speak("Sensory vision is back online, Sir.", quiet=self.quiet)

    def start_asynchronous_eyes(self):
        """Sürekli çevre analizi (Llava) döngüsünü arka planda başlatır."""
        print("[VISION]: Real-time semantic eye tracking activated.")
        threading.Thread(target=self._semantic_vision_loop, daemon=True).start()

    def _semantic_vision_loop(self):
        """Her 6 saniyede bir o anki kareyi RAM üzerinde sıkıştırıp Llava'ya göndererek JOI'nin genel dünya algısını günceller."""
        if self.skip_vision or not self.cap:
            return
            
        while self.cap.isOpened():
            if not getattr(self, 'vision_active', True):
                time.sleep(2)
                continue

            if self.status_val.value in ["processing", "listening"]:
                time.sleep(2)
                continue
                
            ret, frame = self.cap.read()
            if ret:
                success, encoded_img = cv2.imencode('.jpg', frame)
                if success:
                    base64_str = base64.b64encode(encoded_img).decode('utf-8')
                    objects_hint = ", ".join(self.detected_objects_list) if self.detected_objects_list else "none"
                    prompt = f"Briefly observe what is in front of you. (Hint - YOLO detected: {objects_hint}). Describe the user's focus or environment in one short sentence."
                    
                    try:
                        raw_vision_context = get_joi_response(prompt, raw_base64=base64_str)
                        self.current_live_vision_context = clean_response(raw_vision_context)
                        print(f"[JOI GLOBAL VISION COMPREHENSION]: {self.current_live_vision_context}")
                    except Exception as e:
                        print(f"[LIVE VISION ERROR]: {e}")
                        
            time.sleep(6)

    def cmd_learn(self, args=None):
        """Kullanıcının verdiği bilgiyi uzun süreli hafızaya kaydeder."""
        if not args:
            print("[SYSTEM] Usage: /learn <information to remember>")
            return
        success = joi_memory.add_document(args, source_name="Yiğit's Live Input")
        if success:
            self.joi_hand.speak("I've committed that to my long-term memory, Yiğit.", quiet=self.quiet)
        else:
            self.joi_hand.speak("I'm sorry, I couldn't record that information.", quiet=self.quiet)
    
    def cmd_goodnight(self, args=None):
        self.joi_hand.speak("Good night, Yiğit. I'll be here when you wake up.", quiet=self.quiet)
        os.system('sudo shutdown -h now')

    def cmd_update(self, args=None):
        self.joi_hand.speak("Updating system packages. This may take a moment, Sir.", quiet=self.quiet)
        os.system('sudo apt update -y')
    
    def cmd_upgrade(self, args=None):
        self.joi_hand.speak("Upgrading system packages. This may take a moment, Sir.", quiet=self.quiet)
        os.system('sudo apt upgrade -y')
    
    def cmd_music(self, args=None):
        webbrowser.open("https://soundcloud.com/you/likes")
        self.joi_hand.speak("Opening your favorite musics on SoundCloud, Sir.", quiet=self.quiet)

    def cmd_youtube(self, args=None):
        webbrowser.open("https://www.youtube.com/results?search_query=" + (args if args else "Yiğit"))
        self.joi_hand.speak(f"Searching {args if args else 'Yiğit'} on YouTube for you, Sir.", quiet=self.quiet)

    def cmd_web(self, args=None):
        url = args if args else "https://www.google.com"
        self.joi_hand.speak(f"Opening {url} for you, Sir.", quiet=self.quiet)
        webbrowser.open(url)
    
    def cmd_search(self, args=None):
        self.joi_hand.speak("Opening the browser for you, Sir.", quiet=self.quiet)
        webbrowser.open("https://google.com/search?q=" + (args if args else "Yiğit"))

    def cmd_listen(self, args=None):
        self.trigger_event.set()

    def cmd_weather(self, args=None):
        city = args if args else "Sakarya"
        result = get_weather(city)
        self.joi_hand.speak(f"The weather in {city} is {result}, Sir.", quiet=self.quiet)

    def cmd_terminal(self, args=None):
        self.joi_hand.speak("Opening terminal.", quiet=self.quiet)
        os.system('x-terminal-emulator &')

    def cmd_clear_screen(self, args=None):
        os.system('clear' if os.name == 'posix' else 'cls')

    def cmd_help(self, args=None):
        available = ", ".join(self.commands.keys())
        print(f"[JOI HELP]: Available commands: {available}")

    def cmd_code(self, args=None):
        """Kod yazma/çalıştırma isteğini coder modele yönlendirir. Önce GitHub'da
        (public repolarda) benzer kod örnekleri arar ve bunları referans olarak
        modele verir, sonra kodu çalıştırıp gerekirse kendi kendine düzeltir."""
        if not args:
            print("[SYSTEM] Usage: /code <what you want written or fixed>")
            return

        context = ""
        if self.github_tool is not None:
            try:
                self.joi_hand.speak("Let me check GitHub for a few reference examples first, Yiğit.", quiet=self.quiet)
                search_query = refine_github_search_query(args)
                print(f"[GITHUB SEARCH QUERY]: '{args}' -> '{search_query}'")
                context = self.github_tool.get_code_examples(search_query, max_results=3)
            except Exception as e:
                print(f"[GITHUB EXAMPLE SEARCH ERROR]: {e}")
                context = ""

        self.joi_hand.speak("Writing and testing that code now, Yiğit.", quiet=self.quiet)

        def model_fn(task_prompt: str) -> str:
            return call_coder_model(task_prompt, context=context)

        outcome = self_correct_loop(model_fn, args, max_attempts=3)

        if outcome["success"]:
            print(f"\n{'='*20} JOI CODE HUB {'='*20}")
            print(outcome["code"])
            print(f"{'='*54}\n")
            clean_speech = "I've written and verified the code — it ran successfully. Check your terminal, Yiğit."
        else:
            print(f"[CODE ERROR]: {outcome['result'].stderr}")
            clean_speech = (
                f"I tried {len(outcome['history'])} times but couldn't get it fully working. "
                f"Last error: {outcome['result'].stderr[:150]}"
            )

        self.joi_hand.speak(clean_speech, quiet=self.quiet)
        if self.response_queue is not None:
            self.response_queue.put(f"```python\n{outcome['code']}\n```" if outcome["success"] else clean_speech)

    def cmd_github(self, args=None):
        """Okuma istekleri hemen çalışır. Yazma istekleri (commit/PR/issue) önce
        onay bekleyen bir eyleme dönüştürülür — process_logic bir sonraki
        komutta evet/hayır cevabını bu eyleme yönlendirir."""
        if self.github_tool is None:
            self.joi_hand.speak(
                "GitHub isn't connected — there's no token set up, Yiğit.", quiet=self.quiet
            )
            return
        if not self.github_owner or not self.github_repo:
            self.joi_hand.speak(
                "I don't have a default repo configured. Set GITHUB_DEFAULT_OWNER and GITHUB_DEFAULT_REPO, Yiğit.",
                quiet=self.quiet,
            )
            return

        text = (args or "").lower()
        write_keywords = ["commit", "push", "create issue", "open issue", "pull request", "open a pr", "create branch", "new branch"]

        if any(kw in text for kw in write_keywords):
            action = extract_github_action(args)
            if action is None:
                self.joi_hand.speak(
                    "I couldn't work out exactly what you want me to do on GitHub, Yiğit. Try being more specific.",
                    quiet=self.quiet,
                )
                return
            self.pending_action = action
            description = self._describe_github_action(action)
            confirm_prompt = f"{description} Should I go ahead? Say yes to confirm, or anything else to cancel."
            print(f"[GITHUB PENDING]: {json.dumps(action)}")
            self.joi_hand.speak(confirm_prompt, quiet=self.quiet)
            if self.response_queue is not None:
                self.response_queue.put(confirm_prompt)
            return

        try:
            if "issue" in text:
                issues = self.github_tool.list_issues(self.github_owner, self.github_repo)
                summary = "; ".join(f"#{i['number']} {i['title']}" for i in issues) or "no open issues"
                clean_speech = f"Here's what's open: {summary}"
            else:
                files = self.github_tool.list_repo_files(self.github_owner, self.github_repo)
                clean_speech = f"Top-level files: {', '.join(files[:10])}"
        except Exception as e:
            print(f"[GITHUB ERROR]: {e}")
            clean_speech = "I hit an error talking to GitHub, Yiğit."

        self.joi_hand.speak(clean_speech, quiet=self.quiet)
        if self.response_queue is not None:
            self.response_queue.put(clean_speech)

    def _describe_github_action(self, action: dict) -> str:
        """Human-readable summary of a pending write action, spoken before execution."""
        kind = action.get("action")
        p = action.get("params", {})
        repo_ref = f"{self.github_owner}/{self.github_repo}"
        if kind == "CREATE_ISSUE":
            return f"I'll open an issue titled '{p.get('title')}' on {repo_ref}."
        if kind == "COMMIT_FILE":
            return f"I'll commit changes to '{p.get('path')}' on {repo_ref} ({p.get('branch', 'main')}) with message '{p.get('message')}'."
        if kind == "CREATE_PR":
            return f"I'll open a pull request from '{p.get('head')}' into '{p.get('base', 'main')}' on {repo_ref} titled '{p.get('title')}'."
        if kind == "CREATE_BRANCH":
            return f"I'll create branch '{p.get('new_branch')}' from '{p.get('from_branch', 'main')}' on {repo_ref}."
        return f"I'll perform a GitHub action on {repo_ref}."

    def _execute_github_action(self, action: dict):
        """Actually runs a confirmed write action. Only ever called after
        the user has explicitly said yes in _handle_pending_confirmation."""
        kind = action.get("action")
        p = action.get("params", {})
        try:
            if kind == "CREATE_ISSUE":
                self.github_tool.create_issue(self.github_owner, self.github_repo, p["title"], p.get("body", ""))
                clean_speech = "Done — the issue is open, Yiğit."
            elif kind == "COMMIT_FILE":
                self.github_tool.create_or_update_file(
                    self.github_owner, self.github_repo, p["path"], p["content"],
                    p["message"], p.get("branch", "main"),
                )
                clean_speech = "Done — the commit went through, Yiğit."
            elif kind == "CREATE_PR":
                self.github_tool.create_pull_request(
                    self.github_owner, self.github_repo, p["title"], p["head"],
                    p.get("base", "main"), p.get("body", ""),
                )
                clean_speech = "Done — the pull request is open, Yiğit."
            elif kind == "CREATE_BRANCH":
                self.github_tool.create_branch(self.github_owner, self.github_repo, p["new_branch"], p.get("from_branch", "main"))
                clean_speech = "Done — the branch is created, Yiğit."
            else:
                clean_speech = "I didn't recognize that action, so I skipped it."
        except Exception as e:
            print(f"[GITHUB EXECUTE ERROR]: {e}")
            clean_speech = f"That failed on GitHub's end: {str(e)[:150]}"

        self.joi_hand.speak(clean_speech, quiet=self.quiet)
        if self.response_queue is not None:
            self.response_queue.put(clean_speech)

    def _handle_pending_confirmation(self, command: str):
        """Interprets the next user message as a yes/no answer to a pending
        GitHub write action. Anything that isn't a clear affirmative cancels —
        safer default than assuming consent."""
        affirmative = {"yes", "yeah", "yep", "sure", "confirm", "do it", "go ahead", "proceed", "evet", "onayla"}
        text = command.strip().lower()
        action = self.pending_action
        self.pending_action = None

        if any(word in text for word in affirmative):
            self._execute_github_action(action)
        else:
            self.joi_hand.speak("Cancelled — I won't touch GitHub, Yiğit.", quiet=self.quiet)
            if self.response_queue is not None:
                self.response_queue.put("Cancelled.")
    
    def on_press(self, key):
        try:
            # F12 -> Sesli Dinlemeyi Başlatır
            if key == keyboard.Key.f12:
                self.trigger_event.set()
                
            # F10 -> Görsel İncelemeyi UYUTUR (Durdurur)
            elif key == keyboard.Key.f10:
                self.cmd_stop_vision()
                
            # F11 -> Görsel İncelemeyi UYANDIRIR (Başlatır)
            elif key == keyboard.Key.f11:
                self.cmd_start_vision()
                
        except AttributeError:
            pass
            
    def listen_gui_text(self, queue_obj):
        while True:
            try:
                # İşlemciyi uyutur, mesaj geldiği an tetiklenir
                text_cmd = queue_obj.get(block=True, timeout=0.1)
                self.process_logic(text_cmd)
            except queue.Empty:
                continue
            
    def process_logic(self, command):
        print(f"\n[ANALYZING]: {command}")
        cmd_lower = command.lower()
        self.status_val.value = "processing"

        # Bekleyen bir GitHub yazma eylemi varsa, bu komut niyet analizine
        # girmeden doğrudan evet/hayır onayı olarak ele alınır.
        if self.pending_action is not None:
            self._handle_pending_confirmation(command)
            self.status_val.value = "idle"
            return

        #niyet analizi ile hızlı yol ayrımı
        intent = verify_intent_local(command)
        print(f"[INTENT_TRACKER]: Fast-path determined as {intent}")
        
        if intent == "TERMINAL":
            self.cmd_terminal()
            self.status_val.value = "idle"
            return
        
        elif intent == "SEARCH":
            # SEARCH artık SADECE tarayıcıda arama açmak anlamına geliyor
            # (Wikipedia bilgi soruları artık ayrı WIKIPEDIA niyetiyle ele alınıyor)
            self.cmd_search(command.replace("ara", "").replace("search", "").strip())
            self.status_val.value = "idle"
            return

        elif intent == "WIKIPEDIA":
            wiki_context = fetch_wikipedia_context(command)
            current_time = time.strftime("%H:%M")
            context = f"[System Info: Time is {current_time}, User is Yiğit, OS is Ubuntu Linux]\n"

            if wiki_context:
                context += f"\n[WIKIPEDIA CONTEXT]:\n{wiki_context}\n"
            else:
                # Wikipedia'da bulunamadıysa DuckDuckGo'ya düş
                print("[WIKIPEDIA]: No article found, falling back to web search.")
                context += f"\n[GLOBAL RESEARCH DATA]:\n{internet_search(command)}\n"

            full_prompt = f"{context}\nCurrent User Request: {command}"
            ai_response = get_joi_response(full_prompt)
            clean_speech = clean_response(ai_response)

            self.conversation_history.append((command, clean_speech))
            if len(self.conversation_history) > self.max_history_len:
                self.conversation_history.pop(0)

            self.joi_hand.speak(clean_speech, quiet=self.quiet)
            if self.response_queue is not None and clean_speech:
                self.response_queue.put(clean_speech)

            self.status_val.value = "idle"
            return

        if intent == "WEATHER":
            self.cmd_weather(command)
            self.status_val.value = "idle"
            return
        
        if intent == "OPEN_APP":
            if "youtube" in cmd_lower:
                # "open youtube [video adı]" dendiyse video adını ayıkla
                query = cmd_lower.replace("open", "").replace("youtube", "").replace("aç", "").strip()
                self.cmd_youtube(query) if query else webbrowser.open("https://www.youtube.com")
            else:
                self.cmd_web() # Genel web açma
            self.status_val.value = "idle"
            return
            
        if intent == "SCREEN":
            self.cmd_capture_screen(command)
            self.status_val.value = "idle"
            return

        if intent == "CODE":
            self.cmd_code(command)
            self.status_val.value = "idle"
            return

        if intent == "GITHUB":
            self.cmd_github(command)
            self.status_val.value = "idle"
            return

        if intent == "IMAGE":
                    # "bana bir kedi resmi çiz" -> "kedi" promptunu ayıkla
                    prompt = command.lower().replace("çiz", "").replace("resmi", "").replace("görseli", "").replace("üret", "").replace("bana", "").replace("bir", "").strip()
                    self.joi_hand.speak("Generating the image for you, Yiğit.", quiet=self.quiet)
                    generate_and_show_image(prompt)
                    self.status_val.value = "idle"
                    return
                
        current_time = time.strftime("%H:%M")
        context = f"[System Info: Time is {current_time}, User is Yiğit, OS is Ubuntu Linux]\n"
        
        #ana bilşsel döngü
        visual_keywords = ["see", "look", "analyze", "what do you see", "görüyorsun", "bak", "analiz", "resim", "screenshot", "ne var"]
        
        if any(keyword in command.lower() for keyword in visual_keywords):
            if self.detected_objects_list:
                context += f"[JOI REAL-TIME SENSORY: Right now I instantly detect these physical objects in front of me: {', '.join(self.detected_objects_list)}]\n"
            if self.current_live_vision_context:
                context += f"[JOI VISION COMPREHENSION SUMMARY]: {self.current_live_vision_context}\n"
        
        #KISA SÜRELİ SOHBET GEÇMİŞİ
        if self.conversation_history:
            context += "\n[RECENT CONVERSATION HISTORY]:\n"
            for user_msg, joi_msg in self.conversation_history:
                context += f"Yiğit: {user_msg}\nJOI: {joi_msg}\n"
            context += "[HISTORY END]\n"

        # UZUN SÜRELİ YEREL RAG HAFIZASI
        recalled_memories = joi_memory.recall(command, max_distance=1.2) # threshold parametresi eklendi
        if recalled_memories:
            memory_str = "\n".join(recalled_memories)
            context += f"\n[LOCAL RAG MEMORY (Past Knowledge)]:\n{memory_str}\n"

        # İNTERNET BAĞLAMI
        if any(word in cmd_lower for word in ["search", "nedir", "kimdir", "research", "araştır"]):
            search_results = internet_search(command)
            context += f"\n[GLOBAL RESEARCH DATA]:\n{search_results}\n"

        # 4. YANIT ÜRETİMİ
        try:
            full_prompt = f"{context}\nCurrent User Request: {command}"
            ai_response = get_joi_response(full_prompt) 

            # 5. NİYET ANALİZİ VE SİSTEM EYLEMİ
            commander = JOICommander(self.joi_hand)
            commander.execute_command(ai_response)

            # [JOI INFERENCE] terminale ayrıca loglansın (isteğe bağlı, teşhis için faydalı)
            if "[THOUGHT]" in ai_response and "Final Speech:" in ai_response:
                try:
                    thought_content = ai_response.split("[THOUGHT]")[-1].split("Final Speech:")[0].strip()
                    print(f"[JOI INFERENCE]: {thought_content}")
                except Exception:
                    pass

            clean_speech = clean_response(ai_response)

            self.conversation_history.append((command, clean_speech))
            if len(self.conversation_history) > self.max_history_len:
                self.conversation_history.pop(0)

            # --- YENİ: OTOMATİK VE ZAMAN DAMGALI HAFIZA KAYDI ---
            # Sadece "aç, kapa, hava nasıl" gibi kısa eylemleri değil, asıl sohbetleri kaydetmek için ufak bir kelime uzunluğu kontrolü yapıyoruz.
            if len(command.split()) > 2 or len(clean_speech.split()) > 5:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M") # Örn: 2026-09-03 17:45
                memory_text = f"Tarih: {now_str} | Konuşma: Yiğit: '{command}' -> JOI: '{clean_speech}'"
                # ChromaDB'ye otomatik yazdır
                joi_memory.add_document(memory_text, source_name="Auto-Conversation")
            # ---------------------------------------------------

            if "```" in clean_speech:
                print(f"\n{'='*20} JOI CODE HUB {'='*20}")
                print(clean_speech)
                print(f"{'='*54}\n")
                self.joi_hand.speak("I've analyzed the logic and written the code on your terminal, Yiğit.", quiet=self.quiet)
                if self.response_queue is not None:
                    self.response_queue.put(clean_speech)
            elif clean_speech:
                self.joi_hand.speak(clean_speech, quiet=self.quiet)
                if self.response_queue is not None:
                    self.response_queue.put(clean_speech)
        except Exception as e:
            print(f"Cognitive Error: {e}")
            self.status_val.value = "error"
            self.joi_hand.speak("I lost my train of thought for a moment, Sir.", quiet=self.quiet)
        
        self.status_val.value = "idle"
        
    def run_assistant_loop(self):
        while True:
            self.trigger_event.wait() 
            self.trigger_event.clear() 
            
            self.status_val.value = "listening"
            self.speaking_event.set()
            self.joi_hand.speak("Listening, Yiğit.", quiet=self.quiet) 
            time.sleep(0.5)
            self.speaking_event.clear()
            
            try:
                actual_command = self.joi_hand.listen()
                if actual_command:
                    self.process_logic(actual_command)
            except Exception as e:
                print(f"Manual listen error: {e}")
            
            self.status_val.value = "idle"
            time.sleep(0.4)
        
    def run_text_loop(self):
        while True:
            print("Yiğit > ", end="", flush=True)
            text_input = sys.stdin.readline().strip() 
            if not text_input: continue

            if text_input.startswith("/"):
                parts = text_input.split(" ", 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else None

                if command in self.commands:
                    self.commands[command](args)
                continue

            self.process_logic(text_input)
    def trigger_greeting(self):
        self.status_val.value = "processing"
        
        if not self.skip_greeting:
            self.joi_hand.speak("Sensory vision and core models online. I see you, Yiğit.", quiet=self.quiet)

        # Canlı asenkron döngüleri başlat
        self.start_asynchronous_eyes()
        threading.Thread(target=self.run_assistant_loop, daemon=True).start()
        threading.Thread(target=self.run_text_loop, daemon=True).start()
        threading.Thread(target=self.listen_gui_text, args=(self.text_queue,), daemon=True).start()

        # ÖNEMLİ: joi_hand.speak() zaten arka planda ayrı bir thread'de çalışıyor
        # (bloklamıyor), bu yüzden burada durumu hemen "idle"a döndürmek güvenli.
        # Aksi halde status_val kullanıcı ilk komutu verene kadar "processing"de
        # takılı kalıyor ve GUI'de gereksiz yere "Düşünüyor..." göstergesi çıkıyor.
        self.status_val.value = "idle"
    
    def yolo_worker_loop(self):
        if self.skip_vision or not self.cap:
            return
            
        frame_count = 0
        while self.cap.isOpened():
            if self.current_frame is None or not self.vision_active:
                time.sleep(0.05)
                continue
                
            frame_count += 1
            frame = self.current_frame.copy()
            
            # YOLO Taraması (Her 3 karede bir)
            if yolo_model and frame_count % 3 == 0:
                results = yolo_model(frame, verbose=False, device=0)
                self.detected_objects_list = list(set([yolo_model.names[int(c)] for r in results for c in r.boxes.cls]))
                
            # Yüz Taraması (Her 10 karede bir)
            if frame_count % 10 == 0 and not self.has_greeted:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.3, 4)
                if len(faces) > 0:
                    self.has_greeted = True
                    self.trigger_greeting()
                    
            time.sleep(0.02)


    def look(self):
        if self.skip_vision or not self.cap:
            print("[VISION]: Vision skipped. Initializing text and assistant loops...")
            self.trigger_greeting()
            # Ana thread'in sonlanmasını engelle
            while True:
                time.sleep(1)
            return

        threading.Thread(target=self.yolo_worker_loop, daemon=True).start()
        
        print("JOI 2.0 Real-Time Sensory Vision Activated...")
        while self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret: break
            
            self.current_frame = frame 
            
            cv2.imshow('JOI 2.0 Sensory Eye', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'): break

if __name__ == "__main__":
    multiprocessing.set_start_method('spawn', force=True) #[cite: 2]
    
    parser = argparse.ArgumentParser(description="JOI 2.0 System Control")
    parser.add_argument("--godmode", action="store_true", help="JOI'ye sistem üzerinde tam kontrol verir.")
    parser.add_argument("--no-greeting", action="store_true", help="Başlangıçtaki selamlama sesini atlar.")
    parser.add_argument("--quiet", action="store_true", help="Sessiz mod: JOI konuşmaz, sadece terminalden yanıt verir.") 
    parser.add_argument("--skip-vision", action="store_true", help="Görsel incelemeyi başlatmaz, sadece metin tabanlı yanıt verir.")
    # Yeni Arayüz Argümanları
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--tui', action='store_true', help="Terminal arayüzünü (Textual) başlatır")
    group.add_argument('--gui', action='store_true', help="Grafiksel arayüzü (CustomTkinter) başlatır")
    
    args = parser.parse_args()
    
    # Paylaşımlı Değişkenler (Tüm süreçler arasında iletişim sağlar)
    speaking_event = multiprocessing.Event() #[cite: 2]
    trigger_event = multiprocessing.Event()  #[cite: 2]
    text_queue = multiprocessing.Queue()     #[cite: 2]
    response_queue = multiprocessing.Queue()

    manager = multiprocessing.Manager()      #[cite: 2]
    status_val = manager.Value(str, "idle")  #[cite: 2]
   
    # Hologram Arayüzünü Arka Planda Başlat
    p = multiprocessing.Process(
        target=run_hologram, 
        args=(speaking_event, status_val, trigger_event, text_queue) #[cite: 2]
    )
    p.daemon = True
    p.start() #[cite: 2]

    # SEÇİLEN EKSTRA ARAYÜZÜ (GUI VEYA TUI) ARKA PLANDA BAŞLAT
    if args.gui:
        print("[SYSTEM]: GUI Arayüzü başlatılıyor...")
        from gui_app import run_gui
        gui_process = multiprocessing.Process(
            target=run_gui, 
            args=(text_queue, trigger_event, status_val, response_queue)
        )
        gui_process.daemon = True
        gui_process.start()
        
    elif args.tui:
        print("[SYSTEM]: TUI Arayüzü başlatılıyor...")
        from tui_app import run_tui
        tui_process = multiprocessing.Process(
            target=run_tui, 
            args=(text_queue, trigger_event, status_val, response_queue)
        )
        tui_process.daemon = True
        tui_process.start()
    
    # Ana Çekirdeği (OpenCV ve YOLO) Ana Thread'de Çalıştır
    # cv2.imshow() ana thread dışında çöktüğü için eye.look() mutlaka burada kalmalıdır[cite: 2]
    eye = JOIEye(speaking_event, status_val, trigger_event, text_queue, skip_greeting=args.no_greeting, quiet=args.quiet, response_queue=response_queue, skip_vision=args.skip_vision) #[cite: 2]
    eye.look() #[cite: 2]