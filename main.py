import os
import subprocess
import requests
import time
from google import genai
from google.genai import types
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from rembg import remove

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FILE_ID = os.getenv("FILE_ID")
USER_PROMPT = os.getenv("USER_PROMPT")
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "photo")

# Inisialisasi client GenAI
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
    
    if not os.path.exists(file_path):
        raise Exception(f"File hasil edit ({file_path}) tidak ditemukan!")

    with open(file_path, "rb") as f:
        files = {media_type: f}
        res = requests.post(url, data={"chat_id": CHAT_ID}, files=files)
        
    if not res.ok:
        raise Exception(f"Gagal mengunggah ke Telegram: {res.text}")

def change_background_ai(input_file, output_file, bg_prompt):
    input_img = Image.open(input_file).convert("RGBA")
    fg_img = remove(input_img)
    
    if HF_TOKEN:
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        try:
            response = requests.post(API_URL, headers=headers, json={"inputs": bg_prompt}, timeout=30)
            if response.status_code == 200:
                bg_path = "ai_bg.jpg"
                with open(bg_path, "wb") as f:
                    f.write(response.content)
                bg_img = Image.open(bg_path).resize(input_img.size).convert("RGBA")
                bg_img.paste(fg_img, (0, 0), fg_img)
                bg_img.convert("RGB").save(output_file, quality=90, optimize=True)
                return
        except Exception as e:
            print(f"HF Error/Timeout ({e}), fallback ke background putih.")

    background = Image.new("RGBA", input_img.size, (255, 255, 255, 255))
    background.paste(fg_img, (0, 0), fg_img)
    background.convert("RGB").save(output_file, quality=90, optimize=True)

def get_photo_command_from_llm(user_prompt, input_file, output_file):
    system_prompt = (
        f"Kamu adalah pakar Python Pillow profesional. Buat skrip Python murni untuk memproses foto '{input_file}' menjadi '{output_file}'. "
        f"Instruksi user: '{user_prompt}'.\n\n"
        "ATURAN COLOR GRADING / VIVID EDITING:\n"
        "1. Buka gambar: 'img = Image.open(\"{input_file}\").convert(\"RGB\")'\n"
        "2. Jika user minta warna cerah/HD/profesional: tingkatkan Color/Saturasi (1.4 - 1.6), Contrast (1.2 - 1.3), Sharpness (1.5 - 1.8), dan Brightness (1.1).\n"
        "3. Contoh: \n"
        "   img = ImageEnhance.Color(img).enhance(1.5)\n"
        "   img = ImageEnhance.Contrast(img).enhance(1.25)\n"
        "   img = ImageEnhance.Sharpness(img).enhance(1.6)\n"
        "   img = ImageEnhance.Brightness(img).enhance(1.1)\n"
        "4. Selalu simpan di akhir: 'img.save(\"{output_file}\", quality=95, optimize=True)'\n"
        "HANYA berikan baris kode Python murni tanpa markdown, tanpa code block, dan tanpa penjelasan teks."
    )

    models_to_try = [
        'gemini-3.8-flash',
        'gemini-3.6-flash',
        'gemini-2.5-flash',
        'gemini-1.5-flash'
    ]

    # Mengatasi Connection Reset / Network Drop
    max_retries = 3
    for model_name in models_to_try:
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=system_prompt,
                )
                cmd = response.text.strip()
                return cmd.replace("```python", "").replace("```bash", "").replace("```", "").strip()
            except Exception as e:
                print(f"Model {model_name} attempt {attempt+1} gagal ({e}). Retry dalam 2 detik...")
                time.sleep(2)
                continue

    raise Exception("Gagal terhubung ke Google AI API karena gangguan koneksi. Silakan coba kirim ulang.")

def main():
    try:
        send_telegram_message("⚡ GitHub Actions menerima tugas. Memproses foto profesional...")
        
        ext = ".jpg"
        input_file = f"input{ext}"
        output_file = f"output{ext}"
        
        download_telegram_file(FILE_ID, input_file)
        
        if "ganti background" in USER_PROMPT.lower() or "ubah background" in USER_PROMPT.lower():
            send_telegram_message("🎨 Memotong objek dan memproses background AI baru...")
            bg_prompt = USER_PROMPT.lower().replace("ganti background", "").replace("ubah background", "").strip()
            if not bg_prompt:
                bg_prompt = "studio professional background with soft lighting"
            change_background_ai(input_file, output_file, bg_prompt)
        else:
            command = get_photo_command_from_llm(USER_PROMPT, input_file, output_file)
            print(f"Executing command: {command}")
            
            exec_scope = {
                "Image": Image,
                "ImageEnhance": ImageEnhance,
                "ImageFilter": ImageFilter,
                "ImageOps": ImageOps,
                "remove": remove
            }
            exec(command, exec_scope)
            
        upload_telegram_file(output_file, MEDIA_TYPE)
        send_telegram_message("✅ Selesai! Hasil foto editan profesional sudah dikirim di atas.")
        
    except Exception as e:
        send_telegram_message(f"❌ Terjadi kesalahan saat memproses: {str(e)}")

if __name__ == "__main__":
    main()
