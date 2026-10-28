import os
import subprocess
import requests
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FILE_ID = os.getenv("FILE_ID")
USER_PROMPT = os.getenv("USER_PROMPT")
MEDIA_TYPE = os.getenv("MEDIA_TYPE", "video")

genai.configure(api_key=GEMINI_API_KEY)

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

def get_ffmpeg_command_from_llm(user_prompt, input_file, output_file):
    system_instruction = (
        "Kamu adalah pakar FFmpeg. Tugasmu menerjemahkan instruksi user menjadi satu perintah bash FFmpeg yang valid. "
        f"Input file selalu bernama '{input_file}' dan output file bernama '{output_file}'. "
        "HANYA kembalikan perintah FFmpeg murni satu baris tanpa markdown, tanpa code block, dan tanpa penjelasan teks."
    )
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(f"{system_instruction}\n\nInstruksi: {user_prompt}")
    
    cmd = response.text.strip()
    cmd = cmd.replace("```bash", "").replace("```", "").strip()
    return cmd

def main():
    try:
        send_telegram_message("⚡ GitHub Actions menerima tugas. Memproses media...")
        
        ext = ".mp4" if MEDIA_TYPE == "video" else ".jpg"
        input_file = f"input{ext}"
        output_file = f"output{ext}"
        
        download_telegram_file(FILE_ID, input_file)
        
        command = get_ffmpeg_command_from_llm(USER_PROMPT, input_file, output_file)
        print(f"Executing command: {command}")
        
        subprocess.run(command, shell=True, check=True)
        
        upload_telegram_file(output_file, MEDIA_TYPE)
        send_telegram_message("✅ Selesai! Hasil edit sudah dikirim di atas.")
        
    except Exception as e:
        send_telegram_message(f"❌ Terjadi kesalahan saat memproses: {str(e)}")

if __name__ == "__main__":
    main()
