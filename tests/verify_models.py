import sherpa_onnx
import os

def test_load_models():
    # Paraformer Paths
    model_dir = "models/sherpa-onnx-streaming-paraformer-bilingual-zh-en"
    encoder = os.path.join(model_dir, "encoder.int8.onnx")
    decoder = os.path.join(model_dir, "decoder.int8.onnx")
    tokens = os.path.join(model_dir, "tokens.txt")
    
    # VAD Path
    vad_model = "models/silero_vad.onnx"
    
    print("Testing Model Loading...")
    
    # 1. Test ASR Model Loading
    try:
        recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
            encoder=encoder,
            decoder=decoder,
            tokens=tokens,
            num_threads=2,
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
            debug=False
        )
        print("Successfully loaded Streaming Paraformer model.")
    except Exception as e:
        print(f"Failed to load Streaming Paraformer: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. Test VAD Model Loading
    try:
        # Correct VAD configuration for newer sherpa-onnx versions
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = vad_model
        config.silero_vad.threshold = 0.5
        config.silero_vad.min_silence_duration = 0.5
        config.silero_vad.min_speech_duration = 0.25
        config.sample_rate = 16000
        
        vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
        print("Successfully loaded Silero VAD model.")
    except Exception as e:
        print(f"Failed to load Silero VAD: {e}")
        import traceback
        traceback.print_exc()
        return

    print("All models verified successfully!")

if __name__ == "__main__":
    test_load_models()
