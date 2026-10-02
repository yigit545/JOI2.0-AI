import os
from JOI2_0_memory import JOIMemory
from dotenv import load_dotenv

load_dotenv("api.env")
API_KEY = os.getenv("GEMINI_API_KEY")

memory = JOIMemory(api_key=API_KEY)

def load_data_from_folder(folder_path="./knowledge"):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"Lütfen '{folder_path}' klasörüne .txt dosyalarınızı koyun.")
        return

    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            with open(os.path.join(folder_path, filename), "r", encoding="utf-8") as f:
                content = f.read()
                # Metni parçalara (chunks) bölmek RAG kalitesini artırır
                memory.add_document(content, source_name=filename)
                print(f"İşlendi: {filename}")

if __name__ == "__main__":
    load_data_from_folder()