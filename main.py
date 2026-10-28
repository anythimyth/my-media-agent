import os
import subprocess
import requests
from google import genai
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FILE_ID = os.getenv("FILE_ID")
USER_PROMPT = os.getenv("USER_PROMPT")
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "video")

client = genai.Client(api_key=GEMINI_API_KEY)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": text})

def download_telegram_file(file_id, output_path):
    res = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}").json()
    file_path = res["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    
    r = requests.get(file_url, stream=True)
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def upload_telegram_file(file_path, media_type):
    endpoint = "sendVideo" if media_type == "video" else "sendPhoto"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"
    with open(file_path, "rb") as f:
        files = {media_type: f}
        requests.post(url, data={"chat_id": CHAT_ID}, files=files)

def get_command_from_llm(user_prompt, input_file, output_file, media_type):
    if media_type == "photo":
        prompt = (
            f"Kamu adalah pakar Python Pillow. Buat skrip Python yang memproses foto '{input_file}' menjadi '{output_file}'. "
            f"Instruksi user: '{user_prompt}'.\n"
            "ATURAN PENTING PILLOW:\n"
            "1. Jangan pernah panggil img.enhance(). Gunakan kelas seperti ImageEnhance.Sharpness(img).enhance(1.5) atau ImageEnhance.Color(img).enhance(1.2).\n"
            "2. Jangan panggil img.save() di dalam kelas ImageEnhance. Objek penajam harus di-enhance dulu baru disimpan, misal: img = ImageEnhance.Sharpness(img).enhance(1.5)\n"
            "3. Pastikan kode dibuka dengan 'img = Image.open(\"{input_file}\")' dan diakhiri dengan 'img.save(\"{output_file}\")'.\n"
            "HANYA berikan baris kode Python murni tanpa markdown, tanpa code block, dan tanpa penjelasan teks."
        )
    else:
        prompt = (
            f"Kamu adalah pakar FFmpeg. Tugasmu membuat 1 baris perintah bash FFmpeg untuk file input '{input_file}' dan output '{output_file}'. "
            f"Perintah instruksi user: '{user_prompt}'. "
            "HANYA kembalikan perintah FFmpeg murni tanpa markdown."
        )

    # Menggunakan model Gemini Flash standar
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        cmd = response.text.strip()
        cmd = cmd.replace("```python", "").replace("```bash", "").replace("```", "").strip()
        return cmd
    except Exception as e:
        raise Exception(f"Gagal memanggil API Gemini: {str(e)}")

def main():
    try:
        send_telegram_message("⚡ GitHub Actions menerima tugas. Memproses media...")
        
        ext = ".mp4" if MEDIA_TYPE == "video" else ".jpg"
        input_file = f"input{ext}"
        output_file = f"output{ext}"
        
        download_telegram_file(FILE_ID, input_file)
        
        command = get_command_from_llm(USER_PROMPT, input_file, output_file, MEDIA_TYPE)
        print(f"Executing command: {command}")
        
        if MEDIA_TYPE == "photo":
            exec_scope = {
                "Image": Image,
                "ImageEnhance": ImageEnhance,
                "ImageFilter": ImageFilter,
                "ImageOps": ImageOps
            }
            exec(command, exec_scope)
        else:
            subprocess.run(command, shell=True, check=True)
            
        upload_telegram_file(output_file, MEDIA_TYPE)
        send_telegram_message("✅ Selesai! Hasil edit sudah dikirim di atas.")
        
    except Exception as e:
        send_telegram_message(f"❌ Terjadi kesalahan saat memproses: {str(e)}")

if __name__ == "__main__":
    main()
