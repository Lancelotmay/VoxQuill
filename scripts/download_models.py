import os
import requests
import tarfile
import shutil

# Model URLs
PARAFORMER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-streaming-paraformer-bilingual-zh-en.tar.bz2"
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
PUNCT_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12.tar.bz2"

MODELS_DIR = "models"

def download_file(url, dest_folder):
    if not os.path.exists(dest_folder):
        os.makedirs(dest_folder)
    
    filename = url.split('/')[-1]
    file_path = os.path.join(dest_folder, filename)
    
    if os.path.exists(file_path):
        print(f"File {filename} already exists. Skipping download.")
        return file_path

    print(f"Downloading {url}...")
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print(f"Downloaded {filename}")
    else:
        print(f"Failed to download {url}. Status code: {response.status_code}")
        return None
    return file_path

def main():
    # Download VAD model
    download_file(VAD_URL, MODELS_DIR)
    
    # Download Paraformer model
    paraformer_archive = download_file(PARAFORMER_URL, MODELS_DIR)
    if paraformer_archive and paraformer_archive.endswith(".tar.bz2"):
        print(f"Extracting {paraformer_archive}...")
        with tarfile.open(paraformer_archive, "r:bz2") as tar:
            tar.extractall(path=MODELS_DIR)
        print("Paraformer model extraction complete.")

    # Download Punctuation model
    punct_archive = download_file(PUNCT_URL, MODELS_DIR)
    if punct_archive and punct_archive.endswith(".tar.bz2"):
        print(f"Extracting {punct_archive}...")
        with tarfile.open(punct_archive, "r:bz2") as tar:
            tar.extractall(path=MODELS_DIR)
        print("Punctuation model extraction complete.")

if __name__ == "__main__":
    main()
