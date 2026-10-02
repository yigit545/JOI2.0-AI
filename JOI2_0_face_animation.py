import tkinter as tk
import math
import time

class JOIFace:
    def __init__(self, status_val=None, speaking_event=None, trigger_event=None, text_queue=None):
        self.root = tk.Tk()
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        self.root.configure(bg='black')
        
        self.trigger_event = trigger_event
        self.text_queue = text_queue

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        
        # Ekranın dışına taşmayı önlemek için güvenli offset
        window_x = int(sw - 300) if sw > 300 else 0
        window_y = int(sh - 400) if sh > 400 else 0
        self.root.geometry(f"250x280+{window_x}+{window_y}") 

        self.canvas = tk.Canvas(self.root, width=250, height=250, bg='black', highlightthickness=0)
        self.canvas.pack()

        self.entry = tk.Entry(
            self.root, bg="black", fg="#00E1FF", insertbackground="#00E1FF",
            font=("Courier", 10), border=0, highlightthickness=1, highlightcolor="#00E1FF"
        )
        self.entry.pack(side="bottom", fill="x", padx=20, pady=5)
        
        self.entry.bind("<Return>", self.send_text)    
        self.root.bind("<space>", self.manual_trigger) 
        
        self.is_speaking = False
        self.status = "idle"
        self.animation_step = 0

    def manual_trigger(self, event=None):
        """Boşluk tuşuna basıldığında dinleme sinyali gönderir."""
        if self.trigger_event:
            self.trigger_event.set()

    def send_text(self, event=None):
        """Enter tuşuna basıldığında metni kuyruğa atar."""
        text = self.entry.get()
        if text.strip() and self.text_queue:
            self.text_queue.put(text)
            self.entry.delete(0, tk.END) 
            
    def get_color(self):
        colors = {
            "idle": "#00E1FF",       
            "listening": "#FF7C01",  
            "processing": "#FFFF00", 
            "error": "#FF0000"       
        }
        return colors.get(self.status, "#00FFFF")

    def draw(self):
        self.canvas.delete("all")
        cx, cy = 125, 125
        current_color = self.get_color()
        
        if self.is_speaking or self.status == "listening":
            radius = 80 + math.sin(time.time() * 25) * 12
        else:
            radius = 80 + math.sin(self.animation_step) * 3
            
        self.canvas.create_oval(cx-radius, cy-radius, cx+radius, cy+radius, outline=current_color, width=4)
        self.canvas.create_oval(cx-radius-5, cy-radius-5, cx+radius+5, cy+radius+5, outline=current_color, width=1)

    def update(self):
        self.animation_step += 0.1
        self.draw()
        self.root.after(30, self.update)

    def start(self):
        self.update()
        self.root.mainloop()