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
    # Metode Image-to-Image menggunakan Hugging Face
    if HF_TOKEN:
        # Menggunakan model base SDXL yang jauh lebih agresif dalam memanipulasi pemandangan
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        # Format prompt yang meyakinkan AI untuk merombak total cuaca dan warna secara masif
        refined_prompt = (
            f"A magnificent cinematic photo, extremely vivid and rich color grading, HDR 4k, "
            f"bright sunny day with gorgeous deep blue sky, fluffy white clouds, warm natural sunlight illuminating the scene, "
            f"high contrast, highly detailed, professional color correction: {user_prompt}"
        )
        
        try:
            # Hugging Face image-to-image membutuhkan format multipart/form-data agar parameter 'image' dan 'strength' terbaca dengan benar
            with open(input_file, "rb") as f:
                img_bytes = f.read()
                
            # Kita gunakan file upload biner murni dengan prompt disematkan di query/header 
            # atau menggunakan standard payload parameters jika multi-part didukung.
            # Alternatif paling aman tanpa payload error: Kirim gambar dengan headers khusus
            response = requests.post(
                API_URL, 
                headers=headers, 
                files={
                    "image": ("image.jpg", img_bytes, "image/jpeg")
                },
                data={
                    "inputs": refined_prompt,
                    "strength": "0.55"  # Ditingkatkan dari 0.35 agar AI lebih berani merombak warna langit & pencahayaan
                },
                timeout=65
            )
            
            if response.status_code == 200 and len(response.content) > 10000:
                with open(output_file, "wb") as f:
                    f.write(response.content)
                return
            else:
                print(f"HF Server returned status {response.status_code}. Melakukan fallback ke lokal...")
        except Exception as e:
            print(f"HF Image-to-Image gagal ({e}), beralih ke local enhancement...")

    # Fallback/Metode Lokal: Optimasi visual dengan algoritma Pillow yang JAUH lebih agresif
    # (Menggunakan ImageOps & Multi-Pass Contrast/Color Enhancement agar pasti ada perubahan)
    img = Image.open(input_file).convert("RGB")
    
    # 1. Normalisasi & Auto-Contrast otomatis untuk mendongkrak area gelap (shadow/HDR simulation)
    img = ImageOps.autocontrast(img, cutoff=1)
    
    # 2. Dongkrak Color & Contrast secara agresif
    img = ImageEnhance.Color(img).enhance(1.75)       # Sangat-sangat Vivid & berwarna
    img = ImageEnhance.Contrast(img).enhance(1.4)     # Kontras dramatis & dalam
    img = ImageEnhance.Brightness(img).enhance(1.08)   # Sedikit diterangkan agar detail gelap terlihat
    img = ImageEnhance.Sharpness(img).enhance(1.9)    # Sangat tajam
    
    # 3. Lapisan filter detail & edge enhancement
    img = img.filter(ImageFilter.DETAIL)
    img = img.filter(ImageFilter.EDGE_ENHANCE_MORE)   # Memberi kesan 4K/HDR bergaris tajam
    
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
