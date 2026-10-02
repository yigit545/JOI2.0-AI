import requests
from urllib.parse import quote
import subprocess
import os

def generate_and_show_image(prompt, output_file="joi_generated.png"):
    """
    Girilen metinden görsel üretir, diske kaydeder ve varsayılan resim görüntüleyici ile açar.
    """
    try:
        print(f"[IMAGE GEN]: '{prompt}' için görsel üretiliyor...")
        encoded_prompt = quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(output_file, "wb") as f:
                f.write(response.content)
            
            # Linux (Ubuntu) üzerinde resmi varsayılan resim görüntüleyici ile aç
            if os.name == "posix":
                subprocess.Popen(["xdg-open", output_file])
            return True
        else:
            print(f"[IMAGE GEN ERROR]: Sunucu hatası {response.status_code}")
            return False
    except Exception as e:
        print(f"[IMAGE GEN ERROR]: {e}")
        return False