from urllib import response
from duckduckgo_search.cli import text
import requests
import speech_recognition as sr
import edge_tts
import pygame
import asyncio
import os
import time
import threading  # YENİ: Eşzamanlılık kontrolü için eklendi

class JOIControl:
    def __init__(self):
        pygame.mixer.init()
        self.voice = "en-US-AriaNeural" 
        
        # YENİ: Ses dosyalarının üst üste binmesini ve hata vermesini engellemek için kilit
        self.tts_lock = threading.Lock()
        
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 2.0 
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 1.5

        with self.microphone as source:
            print("Sistem ortam gürültüsüne kalibre ediliyor...")
            self.recognizer.adjust_for_ambient_noise(source, duration=2.0)

    def speak(self, text, quiet=False):
        """Metni sese çevirme isteğini doğrudan arka plan thread'ine gönderir."""
        if quiet:
            print(f"[JOI - SILENT]: {text}")
            return
        print(f"JOI: {text}")
    
        # Event loop karmaşasını önlemek için tamamen izole bir thread başlatıyoruz
        threading.Thread(target=self._thread_safe_speak, args=(text,), daemon=True).start()

    def _thread_safe_speak(self, text):
        """Thread Lock kullanarak birden fazla ses isteğini sıraya koyar."""
        with self.tts_lock:
            try:
                # Kendi temiz asenkron döngüsünü oluşturup çalıştırır
                asyncio.run(self._generate_and_play(text))
            except Exception as e:
                print(f"Ses Oynatma Hatası: {e}")

    async def _generate_and_play(self, text):
        """Edge-TTS ile benzersiz ses dosyası üretir ve oynatır."""
        output_file = f"joi_temp_{int(time.time() * 1000)}.mp3"
        
        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(output_file)
        
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        
        pygame.mixer.music.unload()
        
        try:
            if os.path.exists(output_file):
                os.remove(output_file)
        except OSError:
            pass

    def listen(self):
        """Kullanıcıyı dinler ve İngilizce metne çevirir. Sonsuz kilidi engeller."""
        with self.microphone as source:
            print("Listening (I'm waiting for you, Yiğit)...")    
            try:
                # DİKKAT: Sonsuz beklemeyi önlemek için timeout limitleri eklendi!
                # 10 saniye içinde ses gelmezse veya 15 saniyeden uzun konuşulursa keser.
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)
                text = self.recognizer.recognize_google(audio, language='en-US')
                return text
            except sr.WaitTimeoutError:
                print("[SYSTEM] Listening timeout - No speech detected.")
                return None
            except Exception as e:
                print(f"[SYSTEM] Recognition error: {e}")
                return None
    


    def get_quick_location(self):
        try:
        # Ücretsiz bir IP API'si kullanıyoruz
            response = requests.get('https://ipapi.co/json/', timeout=5)
            data = response.json()
            return f"{data.get('city')}, {data.get('region')}"
        except:
            return "Konum bilgisi alınamadı."