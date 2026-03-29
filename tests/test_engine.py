import time
from core.audio import AudioProvider
from core.asr import ASRWorker

def on_partial(text):
    print(f"Partial: {text}", flush=True)

def on_final(text):
    print(f"Final: {text}", flush=True)

def main():
    audio = AudioProvider()
    asr = ASRWorker(audio, on_partial_result=on_partial, on_final_result=on_final)
    
    print("ASR Engine Test Starting...")
    print("Speak into your microphone. Press Ctrl+C to stop.")
    
    audio.start()
    asr.start()
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        asr.stop()
        audio.stop()
        asr.join()

if __name__ == "__main__":
    main()
