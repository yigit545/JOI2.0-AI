from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json

# JOI 2.0 Bileşenlerini İçe Aktar
from JOI2_0_visionv2 import get_joi_response 
from joi_commander import JOICommander        
from JOI2_0_system_control import JOIControl  

# Başlatma işlemleri
joi_hand = JOIControl()
commander = JOICommander(joi_hand)

app = Flask(__name__)
CORS(app)

# HTML Arayüzü
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JOI 2.0 Terminal</title>
    <style>
        body { font-family: 'Courier New', monospace; background: #0a0a0a; color: #00ffcc; padding: 20px; margin: 0; }
        .container { max-width: 600px; margin: auto; }
        h1 { text-align: center; font-size: 1.5rem; text-shadow: 0 0 10px #00ffcc; }
        #chat-log { height: 400px; border: 1px solid #333; overflow-y: auto; padding: 10px; margin-bottom: 20px; background: #000; border-radius: 5px; }
        .user-msg { color: #fff; margin-bottom: 10px; border-left: 3px solid #555; padding-left: 10px; }
        .joi-msg { color: #00ffcc; margin-bottom: 10px; font-weight: bold; border-left: 3px solid #00ffcc; padding-left: 10px; }
        .input-area { display: flex; gap: 10px; }
        input { flex: 1; padding: 12px; border: 1px solid #00ffcc; background: #000; color: #fff; border-radius: 5px; outline: none; }
        button { padding: 12px 20px; background: #00ffcc; color: #000; border: none; font-weight: bold; border-radius: 5px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <h1>JOI 2.0 REMOTE INTERFACE</h1>
        <div id="chat-log"></div>
        <div class="input-area">
            <input type="text" id="cmdInput" placeholder="Yiğit: Komut yazın..." onkeypress="if(event.key==='Enter') send()">
            <button onclick="send()">GÖNDER</button>
        </div>
    </div>

    <script>
        async function send() {
            const input = document.getElementById('cmdInput');
            const log = document.getElementById('chat-log');
            const val = input.value;
            if(!val) return;

            log.innerHTML += `<div class="user-msg"><b>Yiğit:</b> ${val}</div>`;
            input.value = '';
            log.scrollTop = log.scrollHeight;

            try {
                const res = await fetch('/komut', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: val})
                });
                const data = await res.json();
                log.innerHTML += `<div class="joi-msg">JOI: ${data.reply}</div>`;
                log.scrollTop = log.scrollHeight;
            } catch (e) {
                log.innerHTML += `<div style="color:red">Bağlantı Hatası! Sunucu çalışıyor mu?</div>`;
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/komut', methods=['POST'])
def handle_command():
    data = request.get_json()
    user_query = data.get("query", "")

    # AI Yanıtı Üret
    ai_response = get_joi_response(user_query)
    
    # Varsa Komutu Arka Planda Çalıştır
    commander.execute_command(ai_response)

    # Sözel kısmı ayıkla
    clean_reply = ai_response.split("[COMMAND_JSON:")[0].strip()
    
    if not clean_reply and "[COMMAND_JSON:" in ai_response:
        clean_reply = "İsteğinizi hemen yerine getiriyorum, Yiğit."

    return jsonify({"reply": clean_reply})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)