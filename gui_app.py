import customtkinter as ctk
import tkinter.font as tkfont
import time
import random
from datetime import datetime

# Renk paleti
COLORS = {
    "bg": "#000000",
    "user_bubble": "#0f3460",
    "joi_bubble": "#16213e",
    "accent": "#e94560",
    "accent_hover": "#c73650",
    "text": "#eaeaea",
    "muted": "#8b8b9e",
    "listening": "#60a5fa",
    "thinking": "#fbbf24",
}

# Zaman dilimine göre karşılama mesajları — her açılışta o dilimden rastgele biri seçilir
GREETINGS = {
    "morning": [   # 05:00–11:59
        "Günaydın, Yiğit. JOI çevrimiçi.",
        "Sabah şekerlemesi bitti mi? Buradayım, Yiğit.",
        "JOI hazır. Güne nasıl başlıyoruz, Yiğit?",
    ],
    "afternoon": [  # 12:00–17:59
        "İyi günler, Yiğit. JOI çevrimiçi.",
        "JOI hazır. Bir şeyler sor, Yiğit.",
        "Öğleden sonra vardiyası başladı. Buradayım, Yiğit.",
    ],
    "evening": [   # 18:00–22:59
        "İyi akşamlar, Yiğit. JOI çevrimiçi.",
        "Akşam moduna geçtim. Ne yapalım, Yiğit?",
        "JOI hazır, günün nasıl geçti Yiğit?",
    ],
    "night": [     # 23:00–04:59
        "Gece nöbeti başladı. JOI çevrimiçi, Yiğit.",
        "Hâlâ ayakta mısın, Yiğit? Buradayım.",
        "Sessiz saatler... JOI dinliyor, Yiğit.",
    ],
}


def _time_bucket(hour=None):
    hour = datetime.now().hour if hour is None else hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 23:
        return "evening"
    return "night"


def _get_greeting():
    return random.choice(GREETINGS[_time_bucket()])


def _pick_font(preferred=("Roboto", "Inter", "Ubuntu", "Segoe UI", "DejaVu Sans")):
    """Roboto sistemde yoksa sessizce garip bir fonta düşmek yerine,
    mevcut olan ilk fontu seçer."""
    available = set(tkfont.families())
    for name in preferred:
        if name in available:
            return name
    return "TkDefaultFont"


def run_gui(text_queue, trigger_event, status_val, response_queue=None):
    """
    text_queue      : Kullanıcının yazdığı mesajları ana sürece gönderir (mevcut).
    trigger_event   : Mikrofon dinlemeyi tetikler (mevcut).
    status_val      : idle / listening / processing / error durumunu okur (mevcut).
    response_queue  : (opsiyonel) JOI'nin ürettiği cevap metinlerini GUI'ye
                       göndermek için kullanılır.
    """
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    class JOIGUI(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("JOI 2.0")
            self.geometry("900x650")
            self.minsize(600, 450)
            self.configure(fg_color=COLORS["bg"])

            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)

            self.font_family = _pick_font()
            self._row = 0
            self._message_labels = []   # (label, is_user) — wraplength'i pencere boyutuna göre güncellemek için
            self._is_processing = False
            self._thinking_container = None
            self._thinking_dots_job = None
            self._last_status = "idle"
            self._greeting_container = None

            self._build_header()
            self._build_chat_area()
            self._build_input_area()

            self._add_hero_greeting(_get_greeting())

            self.bind("<Control-l>", lambda e: self._clear_chat())
            self.bind("<Configure>", self._on_resize)
            self.after(100, lambda: self.entry.focus_set())

            self.after(400, self._poll_status)
            if response_queue is not None:
                self.after(300, self._poll_responses)

        # ---------------- Üst Bilgi ----------------
        def _build_header(self):
            header = ctk.CTkFrame(self, fg_color="transparent", height=70)
            header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 0))
            header.grid_columnconfigure(0, weight=1)

            title_frame = ctk.CTkFrame(header, fg_color="transparent")
            title_frame.grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(
                title_frame, text="JOI", font=(self.font_family, 26, "bold"),
                text_color=COLORS["accent"]
            ).pack(side="left")
            ctk.CTkLabel(
                title_frame, text="  2.0", font=(self.font_family, 26),
                text_color=COLORS["text"]
            ).pack(side="left")

            right_frame = ctk.CTkFrame(header, fg_color="transparent")
            right_frame.grid(row=0, column=1, sticky="e")

            self.status_dot = ctk.CTkLabel(
                right_frame, text="● Hazır", font=(self.font_family, 13),
                text_color="#4ade80"
            )
            self.status_dot.pack(side="left", padx=(0, 14))

            ctk.CTkButton(
                right_frame, text="Temizle", width=70, height=28, corner_radius=14,
                fg_color="transparent", border_width=1, border_color=COLORS["muted"],
                hover_color=COLORS["joi_bubble"], text_color=COLORS["muted"],
                font=(self.font_family, 11), command=self._clear_chat
            ).pack(side="left")

        # ---------------- Sohbet Alanı ----------------
        def _build_chat_area(self):
            self.chat_scroll = ctk.CTkScrollableFrame(
                self, fg_color=COLORS["bg"], corner_radius=0
            )
            self.chat_scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
            self.chat_scroll.grid_columnconfigure(0, weight=1)

        # ---------------- Giriş Alanı ----------------
        def _build_input_area(self):
            input_row = ctk.CTkFrame(self, fg_color="transparent")
            input_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
            input_row.grid_columnconfigure(0, weight=1)

            # Çok satırlı giriş: Enter gönderir, Shift+Enter yeni satır ekler
            self.entry = ctk.CTkTextbox(
                input_row, height=50, corner_radius=25, font=(self.font_family, 14),
                fg_color=COLORS["joi_bubble"], text_color=COLORS["text"],
                border_width=0, wrap="word"
            )
            self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
            self.entry.bind("<Return>", self._on_return)
            self.entry.bind("<Shift-Return>", lambda e: None)  # varsayılan davranışa izin ver (yeni satır)

            self.mic_button = ctk.CTkButton(
                input_row, text="\U0001F3A4", width=50, height=50, corner_radius=25,
                fg_color=COLORS["joi_bubble"], hover_color=COLORS["user_bubble"],
                command=self.trigger_listen
            )
            self.mic_button.grid(row=0, column=1, padx=(0, 10))

            self.send_button = ctk.CTkButton(
                input_row, text="Gönder", width=90, height=50, corner_radius=25,
                fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                font=(self.font_family, 14, "bold"),
                command=lambda: self.send_message(None)
            )
            self.send_button.grid(row=0, column=2)

        def _on_return(self, event):
            # Shift basılı değilse gönder, satır ekleme
            self.send_message(event)
            return "break"

        # ---------------- Mesaj Balonları ----------------
        def _current_wraplength(self):
            # Balon genişliğini pencere genişliğinin yaklaşık %55'i olacak şekilde ayarla
            width = max(self.winfo_width(), 600)
            return int(width * 0.55)

        def _add_bubble(self, text, sender="joi"):
            self._remove_greeting()  # ilk gerçek mesajla birlikte hero karşılama kaybolur

            is_user = sender == "user"
            bubble_color = COLORS["user_bubble"] if is_user else COLORS["joi_bubble"]
            anchor = "e" if is_user else "w"
            justify = "right" if is_user else "left"

            container = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
            container.grid(row=self._row, column=0, sticky="ew", pady=4)
            container.grid_columnconfigure(0, weight=1)

            bubble = ctk.CTkFrame(container, fg_color=bubble_color, corner_radius=16)
            bubble.grid(row=0, column=0, sticky=anchor,
                        padx=(80, 0) if is_user else (0, 80))

            label = ctk.CTkLabel(
                bubble, text=text, font=(self.font_family, 14), text_color=COLORS["text"],
                justify=justify, wraplength=self._current_wraplength()
            )
            label.pack(padx=14, pady=10)
            self._message_labels.append(label)

            ctk.CTkLabel(
                container, text=time.strftime("%H:%M"), font=(self.font_family, 10),
                text_color=COLORS["muted"]
            ).grid(row=1, column=0, sticky=anchor,
                   padx=(80, 4) if is_user else (4, 80))

            self._row += 2
            self.after(50, self._scroll_to_bottom)
            return container

        def _add_system_message(self, text):
            ctk.CTkLabel(
                self.chat_scroll, text=text, font=(self.font_family, 12, "italic"),
                text_color=COLORS["muted"]
            ).grid(row=self._row, column=0, pady=8)
            self._row += 1
            self.after(50, self._scroll_to_bottom)

        def _add_hero_greeting(self, text):
            """Büyük, ortalanmış, mavi 'glow' efektli açılış mesajı.
            İlk gerçek mesaj gönderildiğinde otomatik olarak kaybolur."""
            self._remove_greeting()

            wrapper = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
            wrapper.grid(row=self._row, column=0, sticky="ew", pady=(30, 30))
            wrapper.grid_columnconfigure(0, weight=1)

            # Katmanlı halo: en dıştan içe doğru gittikçe parlaklaşan mavi tonlar,
            # tkinter'da gerçek blur olmadığı için "glow" hissini böyle simüle ediyoruz.
            outer_glow = ctk.CTkFrame(wrapper, fg_color="#132a43", corner_radius=32)
            outer_glow.grid(row=0, column=0)  # sticky yok -> hücre içinde otomatik ortalanır

            mid_glow = ctk.CTkFrame(outer_glow, fg_color="#1c3f66", corner_radius=26)
            mid_glow.pack(padx=10, pady=10)

            inner_card = ctk.CTkFrame(
                mid_glow, fg_color=COLORS["joi_bubble"], corner_radius=20,
                border_width=2, border_color=COLORS["listening"]
            )
            inner_card.pack(padx=6, pady=6)

            ctk.CTkLabel(
                inner_card, text=text, font=(self.font_family, 22, "bold"),
                text_color="#93c5fd", justify="center"
            ).pack(padx=36, pady=22)

            self._greeting_container = wrapper
            self._row += 1
            self.after(50, self._scroll_to_bottom)

        def _remove_greeting(self):
            if self._greeting_container is not None:
                try:
                    self._greeting_container.destroy()
                except Exception:
                    pass
                self._greeting_container = None

        def _scroll_to_bottom(self):
            try:
                canvas = self.chat_scroll._parent_canvas
                canvas.update_idletasks()
                canvas.yview_moveto(1.0)
            except Exception:
                pass

        def _clear_chat(self):
            for child in self.chat_scroll.winfo_children():
                child.destroy()
            self._message_labels = []
            self._greeting_container = None
            self._row = 0
            self._add_system_message("Sohbet temizlendi.")

        # ---------------- "Düşünüyor..." Göstergesi ----------------
        def _show_thinking(self):
            if self._thinking_container is not None:
                return
            self._thinking_container = self._add_bubble("●", sender="joi")
            self._animate_thinking(0)

        def _animate_thinking(self, tick):
            if self._thinking_container is None:
                return
            dots = "●" * ((tick % 3) + 1)
            try:
                label = self._thinking_container.winfo_children()[0].winfo_children()[0]
                label.configure(text=dots)
            except Exception:
                pass
            self._thinking_dots_job = self.after(450, lambda: self._animate_thinking(tick + 1))

        def _hide_thinking(self):
            if self._thinking_dots_job is not None:
                self.after_cancel(self._thinking_dots_job)
                self._thinking_dots_job = None
            if self._thinking_container is not None:
                self._thinking_container.destroy()
                self._thinking_container = None
                self._row -= 2

        # ---------------- Olaylar ----------------
        def send_message(self, event):
            if self._is_processing:
                return  # JOI hâlâ öncekini işlerken yeni mesajı engelle
            text = self.entry.get("1.0", "end").strip()
            if text:
                self._add_bubble(text, sender="user")
                text_queue.put(text)
                self.entry.delete("1.0", "end")

        def trigger_listen(self):
            trigger_event.set()
            self._add_system_message("\U0001F3A4 Dinleniyor...")

        def _on_resize(self, event):
            # Sadece ana pencere yeniden boyutlandığında ve genişlik gerçekten değiştiğinde tepki ver
            if event.widget is not self:
                return
            new_wrap = self._current_wraplength()
            for label in self._message_labels:
                try:
                    label.configure(wraplength=new_wrap)
                except Exception:
                    pass

        # ---------------- Durum / Yanıt Döngüleri ----------------
        def _poll_status(self):
            current_status = status_val.value
            status_map = {
                "idle": ("● Hazır", "#4ade80"),
                "listening": ("● Dinleniyor...", COLORS["listening"]),
                "processing": ("● Düşünüyor...", COLORS["thinking"]),
                "error": ("● Hata", "#f87171"),
            }
            text, color = status_map.get(current_status, ("● Bilinmiyor", COLORS["muted"]))
            self.status_dot.configure(text=text, text_color=color)

            self._is_processing = current_status in ("processing", "listening")
            self.send_button.configure(state="disabled" if self._is_processing else "normal")
            self.mic_button.configure(
                fg_color=COLORS["listening"] if current_status == "listening" else COLORS["joi_bubble"]
            )

            if current_status == "processing" and self._last_status != "processing":
                self._show_thinking()
            elif current_status != "processing" and self._thinking_container is not None:
                self._hide_thinking()

            self._last_status = current_status
            self.after(400, self._poll_status)

        def _poll_responses(self):
            try:
                while not response_queue.empty():
                    joi_text = response_queue.get_nowait()
                    if joi_text:
                        self._hide_thinking()
                        self._add_bubble(joi_text, sender="joi")
            except Exception:
                pass
            self.after(300, self._poll_responses)

    app = JOIGUI()
    app.mainloop()