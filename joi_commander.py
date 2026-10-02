from joi_image_gen import generate_and_show_image
import json
import subprocess
import webbrowser
from datetime import datetime
import file_manager
import system_monitor
import package_manager

# pywhatkit içe aktarılırken internet kontrolü yaptığı için try-except bloğuna alıyoruz
try:
    import pywhatkit as kit
    PYWHATKIT_AVAILABLE = True
except Exception as e:
    print(f"Uyarı: İnternet bağlantısı yok. pywhatkit devre dışı bırakıldı. Hata: {e}")
    PYWHATKIT_AVAILABLE = False
from joi_image_gen import generate_and_show_image
import json
import subprocess
import webbrowser
from datetime import datetime


# pywhatkit içe aktarılırken internet kontrolü yaptığı için try-except bloğuna alıyoruz
try:
    import pywhatkit as kit
    PYWHATKIT_AVAILABLE = True
except Exception as e:
    print(f"Uyarı: İnternet bağlantısı yok. pywhatkit devre dışı bırakıldı. Hata: {e}")
    PYWHATKIT_AVAILABLE = False

class JOICommander:
    def __init__(self, joi_control):
        self.joi_control = joi_control # JOIControl nesnesi

    def execute_command(self, ai_response):
        """AI yanıtındaki JSON komutunu ayıklar ve çalıştırır."""
        if "[COMMAND_JSON:" in ai_response:
            try:
                json_part = ai_response.split("[COMMAND_JSON:")[1].split("]")[0]
                cmd_data = json.loads(json_part)
                
                action = cmd_data.get("action")
                params = cmd_data.get("params")

                if action == "OPEN_APP":
                    if params == "terminal":
                        subprocess.Popen(['x-terminal-emulator'])
                    elif params == "browser":
                        webbrowser.open("https://www.google.com")
                    elif params == "youtube":
                        webbrowser.open("https://www.youtube.com")
                
                elif action == "SEND_WHATSAPP":
                    if PYWHATKIT_AVAILABLE:
                        phone = params.get("phone")
                        msg = params.get("message")
                        kit.sendwhatmsg_instantly(phone, msg, wait_time=0.5, tab_close=True)
                        return f"WhatsApp mesajı gönderildi: {msg}"
                    else:
                        print("İnternet bağlantısı olmadığı için WhatsApp mesajı es geçildi.")
                        return "HATA: İnternet bağlantısı yok."
                    
                elif action == "GENERATE_IMAGE":
                    prompt_text = params if isinstance(params, str) else str(params)
                    success = generate_and_show_image(prompt_text)
                    if success:
                        return f"Görsel üretildi ve ekrana getirildi: {prompt_text}"
                    else:
                        return "Görsel üretilirken bir hata oluştu."
                    
                elif action == "SEARCH":
                    webbrowser.open(f"https://www.google.com/search?q={params}")

            except Exception as e:
                print(f"Command Execution Error: {e}")
        return None
class JOICommander:
    def __init__(self, joi_control):
        self.joi_control = joi_control # JOIControl nesnesi

    def execute_command(self, ai_response):
        """AI yanıtındaki JSON komutunu ayıklar ve çalıştırır."""
        if "[COMMAND_JSON:" in ai_response:
            try:
                json_part = ai_response.split("[COMMAND_JSON:")[1].split("]")[0]
                cmd_data = json.loads(json_part)
                
                action = cmd_data.get("action")
                params = cmd_data.get("params")

                if action == "OPEN_APP":
                    if params == "terminal":
                        subprocess.Popen(['x-terminal-emulator'])
                    elif params == "browser":
                        webbrowser.open("https://www.google.com")
                    elif params == "youtube":
                        webbrowser.open("https://www.youtube.com")

                elif action == "FILE_MANAGE":
                    return file_manager(params if isinstance(params, dict) else {})
 
                elif action == "SYSTEM_STATUS":
                    return system_monitor({"action": "status"})
 
                elif action == "PACKAGE_MANAGE":
                    return package_manager(params if isinstance(params, dict) else {"action": "check"})
                
                elif action == "SEND_WHATSAPP":
                    if PYWHATKIT_AVAILABLE:
                        phone = params.get("phone")
                        msg = params.get("message")
                        kit.sendwhatmsg_instantly(phone, msg, wait_time=0.5, tab_close=True)
                        return f"WhatsApp mesajı gönderildi: {msg}"
                    else:
                        print("İnternet bağlantısı olmadığı için WhatsApp mesajı es geçildi.")
                        return "HATA: İnternet bağlantısı yok."
                    
                elif action == "GENERATE_IMAGE":
                    prompt_text = params if isinstance(params, str) else str(params)
                    success = generate_and_show_image(prompt_text)
                    if success:
                        return f"Görsel üretildi ve ekrana getirildi: {prompt_text}"
                    else:
                        return "Görsel üretilirken bir hata oluştu."
                    
                elif action == "SEARCH":
                    webbrowser.open(f"https://www.google.com/search?q={params}")

            except Exception as e:
                print(f"Command Execution Error: {e}")
        return None