import os
import subprocess
import requests
from google import genai
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from rembg import remove

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FILE_ID = os.getenv("FILE_ID")
USER_PROMPT = os.getenv("USER_PROMPT")
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "photo")

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
    # 1. Hapus background objek utama
    input_img = Image.open(input_file).convert("RGBA")
    fg_img = remove(input_img)
    
    # 2. Jika ada HF_TOKEN, generate background AI via SDXL/FLUX
    if HF_TOKEN:
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        response = requests.post(API_URL, headers=headers, json={"inputs": bg_prompt})
        if response.status_code == 200:
            bg_path = "ai_bg.jpg"
            with open(bg_path, "wb") as f:
                f.write(response.content)
            bg_img = Image.open(bg_path).resize(input_img.size).convert("RGBA")
            bg_img.paste(fg_img, (0, 0), fg_img)
            bg_img.convert("RGB").save(output_file, quality=90, optimize=True)
            return

    # Fallback jika tanpa HF_TOKEN: Gunakan warna background putih/transparan bersih
    background = Image.new("RGBA", input_img.size, (255, 255, 255, 255))
    background.paste(fg_img, (0, 0), fg_img)
    background.convert("RGB").save(output_file, quality=90, optimize=True)

def get_photo_command_from_llm(user_prompt, input_file, output_file):
    system_prompt = (
        f"Kamu adalah pakar Python Pillow profesional. Buat skrip Python murni untuk memproses foto '{input_file}' menjadi '{output_file}'. "
        f"Instruksi user: '{user_prompt}'.\n\n"
        "ATURAN SINTAKS PILLOW WAJIB:\n"
        "1. Selalu buka gambar: 'img = Image.open(\"{input_file}\").convert(\"RGB\")'\n"
        "2. Peningkatan kualitas/penajaman: 'img = ImageEnhance.Sharpness(img).enhance(1.5)'\n"
        "3. Warna/Kontras/Brightness: 'img = ImageEnhance.Color(img).enhance(1.2)', 'img = ImageEnhance.Contrast(img).enhance(1.1)'\n"
        "4. Pembesaran/Resize: Maksimal resolusi 3840x2160 dengan 'Image.Resampling.LANCZOS' agar file <10MB.\n"
        "5. Hapus Background biasa: 'img = remove(img)'\n"
        "6. Selalu simpan di akhir: 'img.save(\"{output_file}\", quality=90, optimize=True)'\n"
        "HANYA berikan baris kode Python murni tanpa markdown, tanpa code block, dan tanpa penjelasan teks."
    )

    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=system_prompt,
    )
    cmd = response.text.strip()
    return cmd.replace("```python", "").replace("```bash", "").replace("```", "").strip()

def main():
    try:
        send_telegram_message("⚡ GitHub Actions menerima tugas. Memproses foto profesional...")
        
        ext = ".jpg"
        input_file = f"input{ext}"
        output_file = f"output{ext}"
        
        download_telegram_file(FILE_ID, input_file)
        
        # Fitur Ganti Background AI
        if "ganti background" in USER_PROMPT.lower() or "ubah background" in USER_PROMPT.lower():
            send_telegram_message("🎨 Memotong objek dan memproses background AI baru...")
            bg_prompt = USER_PROMPT.lower().replace("ganti background", "").replace("ubah background", "").strip()
            if not bg_prompt:
                bg_prompt = "studio professional background with soft lighting"
            change_background_ai(input_file, output_file, bg_prompt)
        else:
            # Fitur Editan Profesional Umum (Pillow + Rembg)
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
