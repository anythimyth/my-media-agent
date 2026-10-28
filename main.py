import os
import subprocess
import requests
import time
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

def advanced_image_enhance(input_file, output_file, user_prompt):
    # Kami manfaatkan Gemini 2.5 Flash untuk menganalisis dan menginstruksikan modifikasi visual
    # yang luar biasa akurat berdasarkan foto aslimu.
    try:
        img_input = Image.open(input_file).convert("RGB")
        
        # Kirim foto asli ke Gemini untuk mendeskripsikan ulang & mendesain modifikasi dalam resolusi tinggi
        prompt_enhancer = (
            "Analisislah foto ini. Sebagai editor profesional, buat skrip Python murni menggunakan Pillow yang akan: "
            "1. Meningkatkan pencahayaan secara drastis (HDR look) dengan kurva yang cerah.\n"
            "2. Mengubah bagian langit yang mendung menjadi biru kaya dengan awan cerah natural secara digital menggunakan manipulasi ImageEnhance dan filtering.\n"
            "3. Meningkatkan saturasi warna tanaman hijau dan kebiruan meja/tenda secara ekstrim agar sangat cerah (vivid).\n"
            "4. Pertahankan keaslian bentuk gelas dan bakso, namun buat detailnya sangat tajam.\n"
            f"Gunakan file input '{input_file}' dan simpan hasilnya di '{output_file}'. "
            "Ingat, berikan output HANYA baris kode python murni, tanpa penjelasan, tanpa ``` atau markdown."
        )

        # Gemini 2.5 Flash memiliki kemampuan visual gila-gilaan yang gratis
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[img_input, prompt_enhancer]
        )
        
        script_code = response.text.strip()
        script_code = script_code.replace("```python", "").replace("```", "").strip()
        
        print(f"Executing AI-generated visual enhancement code: {script_code}")
        
        # Eksekusi skrip grading visual hasil rekomendasi Gemini
        exec_scope = {
            "Image": Image,
            "ImageEnhance": ImageEnhance,
            "ImageFilter": ImageFilter,
            "ImageOps": ImageOps,
            "remove": remove
        }
        exec(script_code, exec_scope)
        return
        
    except Exception as e:
        print(f"Proses AI Visual gagal ({e}), menggunakan fallback manual...")

    # Fallback yang benar-benar kuat untuk memaksa warna biru dan cerah keluar
    img = Image.open(input_file).convert("RGB")
    
    # Gunakan ImageOps untuk menyamakan warna & Auto-Contrast yang sangat agresif
    img = ImageOps.autocontrast(img, cutoff=0.5)
    
    # 1. Naikkan Exposure (Kecerahan)
    img = ImageEnhance.Brightness(img).enhance(1.12)
    
    # 2. Naikkan warna/Saturasi gila-gilaan (memancing warna langit & tenda keluar)
    img = ImageEnhance.Color(img).enhance(1.8)
    
    # 3. Kontras tajam yang seimbang (HDR)
    img = ImageEnhance.Contrast(img).enhance(1.3)
    img = ImageEnhance.Sharpness(img).enhance(1.9)
    
    img.save(output_file, quality=95, optimize=True)

def get_photo_command_from_llm(user_prompt, input_file, output_file):
    # Digunakan untuk prompt biasa yang tidak mengaktifkan pipeline vivid/advanced
    system_prompt = (
        f"Kamu adalah pakar Python Pillow profesional. Buat skrip Python murni untuk memproses foto '{input_file}' menjadi '{output_file}'. "
        f"Instruksi user: '{user_prompt}'.\n\n"
        "ATURAN SINTAKS PILLOW WAJIB:\n"
        "1. Selalu buka gambar: 'img = Image.open(\"{input_file}\").convert(\"RGB\")'\n"
        "2. Peningkatan kualitas/penajaman: 'img = ImageEnhance.Sharpness(img).enhance(1.8)'\n"
        "3. Warna/Kontras/Brightness: 'img = ImageEnhance.Color(img).enhance(1.5)', 'img = ImageEnhance.Contrast(img).enhance(1.25)'\n"
        "4. Pembesaran/Resize: Maksimal resolusi 3840x2160 dengan 'Image.Resampling.LANCZOS' agar file <10MB.\n"
        "5. Hapus Background biasa: 'img = remove(img)'\n"
        "6. Selalu simpan di akhir: 'img.save(\"{output_file}\", quality=95, optimize=True)'\n"
        "HANYA berikan baris kode Python murni tanpa markdown, tanpa code block, dan tanpa penjelasan teks."
    )

    models_to_try = ['gemini-3.8-flash', 'gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']
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
                print(f"Model {model_name} attempt {attempt+1} gagal ({e}). Retry...")
                time.sleep(2)
                continue
    raise Exception("Gagal terhubung ke Google AI API.")

def main():
    try:
        send_telegram_message("⚡ GitHub Actions menerima tugas. Memproses foto profesional...")
        
        ext = ".jpg"
        input_file = f"input{ext}"
        output_file = f"output{ext}"
        
        download_telegram_file(FILE_ID, input_file)
        
        # Logika khusus untuk prompt estetik, vivid, cerah, HDR (memanggil Advanced Image-to-Image)
        trigger_words = ["cerah", "vivid", "kontras", "hdr", "biru", "profesional", "hd", "4k"]
        if MEDIA_TYPE == "photo" and any(word in USER_PROMPT.lower() for word in trigger_words):
            send_telegram_message("🎨 Memproses Advanced Image-to-Image dengan manipulasi langit & pencahayaan...")
            advanced_image_enhance(input_file, output_file, USER_PROMPT)
        else:
            # Fitur Editan Umum / Standar
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
