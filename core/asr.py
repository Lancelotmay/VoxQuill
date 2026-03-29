from core.asr_config import load_asr_config
from core.asr_streaming_online import StreamingOnlineASRWorker
from core.asr_vad_offline import VadOfflineASRWorker


def ASRWorker(
    audio_provider,
    on_partial_result=None,
    on_final_result=None,
    on_finished=None,
    model_id=None,
):
    model_config = load_asr_config(model_id=model_id)
    callbacks = {
        "on_partial_result": on_partial_result,
        "on_final_result": on_final_result,
        "on_finished": on_finished,
    }

    pipeline = model_config["pipeline"]
    if pipeline == "streaming_online":
        return StreamingOnlineASRWorker(audio_provider, model_config, **callbacks)

    if pipeline == "vad_offline":
        return VadOfflineASRWorker(audio_provider, model_config, **callbacks)

    raise ValueError(f"Unsupported ASR pipeline: {pipeline}")
