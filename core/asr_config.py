import json
import os
import shutil
import tarfile
from urllib.parse import urlparse

import requests


from core.path_utils import get_config_path, get_models_dir


DEFAULT_CONFIG_PATH = get_config_path("models.json")
MODELS_DIR = get_models_dir()
_VALIDATION_CACHE = {}


def _load_config_data(path=DEFAULT_CONFIG_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(f"ASR config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config_data(data, path=DEFAULT_CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_path(path_value):
    if not path_value:
        return path_value
    if os.path.isabs(path_value):
        return path_value
    return os.path.abspath(path_value)


def _download_filename(item):
    filename = item.get("filename")
    if filename:
        return filename
    parsed = urlparse(item["url"])
    return os.path.basename(parsed.path)


def _download_dest(item, base_dir=MODELS_DIR):
    dest_folder = item.get("dest", base_dir)
    return _resolve_path(dest_folder)


def _iter_required_files(model_config):
    paths = model_config.get("paths", {})
    for key, value in paths.items():
        if not value or key in ("hr_rule_fsts", "hr_lexicon"):
            continue
        yield _resolve_path(value)

    vad_cfg = model_config.get("vad", {})
    if vad_cfg.get("enabled", True) and vad_cfg.get("model"):
        yield _resolve_path(vad_cfg["model"])

    punct_cfg = model_config.get("punct", {})
    if punct_cfg.get("enabled") and punct_cfg.get("model"):
        yield _resolve_path(punct_cfg["model"])


def _iter_downloaded_artifacts(model_config, base_dir=MODELS_DIR):
    for item in model_config.get("downloads", []):
        archive_path = os.path.join(_download_dest(item, base_dir), _download_filename(item))
        yield os.path.abspath(archive_path)


def _iter_model_dirs(model_config):
    dirs = set()
    for path_value in _iter_required_files(model_config):
        dirs.add(os.path.dirname(path_value))
    return sorted(dirs, key=len, reverse=True)


def load_asr_config(path=DEFAULT_CONFIG_PATH, model_id=None):
    data = _load_config_data(path)
    models = data.get("models", {})
    if not isinstance(models, dict) or not models:
        raise ValueError("ASR config must contain a non-empty 'models' object")

    active_model = model_id or data.get("active_model")
    if not active_model:
        active_model = next(iter(models.keys()))

    if active_model not in models:
        raise ValueError(f"Active model '{active_model}' is not defined in config")

    model = dict(models[active_model])
    if "pipeline" not in model:
        raise ValueError(f"Model '{active_model}' is missing required field 'pipeline'")

    model["id"] = active_model
    # Merge global language preference
    global_langs = data.get("global_languages", ["zh", "en", "ja", "ko", "yue"])
    # If the model uses SenseVoice, we map the list to a compatible string
    # For simplicity, if multiple are selected, we use "auto"
    # If only one is selected, we use that one.
    if "decode" not in model: model["decode"] = {}
    if len(global_langs) == 1:
        model["decode"]["language"] = global_langs[0]
    else:
        model["decode"]["language"] = "auto"

    return model


def get_missing_files(model_config):
    return [path for path in _iter_required_files(model_config) if not os.path.exists(path)]


def is_model_ready(model_config):
    return len(get_missing_files(model_config)) == 0


def _model_cache_key(model_config, deep=False):
    required = list(_iter_required_files(model_config))
    mtimes = []
    for path in required:
        if os.path.exists(path):
            mtimes.append((path, os.path.getmtime(path)))
        else:
            mtimes.append((path, None))
    return (model_config["id"], deep, tuple(mtimes))


def validate_model_loadable(model_config, deep=False):
    if not is_model_ready(model_config):
        return False, "Required files are missing."

    cache_key = _model_cache_key(model_config, deep=deep)
    cached = _VALIDATION_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not deep:
        # Default to True if files exist, avoiding heavy model instantiation during UI listing.
        return True, ""

    try:
        import sherpa_onnx

        if model_config["pipeline"] == "streaming_online":
            paths = model_config["paths"]
            decode = model_config.get("decode", {})
            endpoint = model_config.get("endpoint", {})
            sherpa_onnx.OnlineRecognizer.from_paraformer(
                encoder=paths["encoder"],
                decoder=paths["decoder"],
                tokens=paths["tokens"],
                num_threads=int(decode.get("num_threads", 4)),
                sample_rate=int(model_config.get("sample_rate", 16000)),
                feature_dim=int(model_config.get("feature_dim", 80)),
                decoding_method=decode.get("decoding_method", "greedy_search"),
                debug=False,
                enable_endpoint_detection=bool(endpoint.get("enabled", True)),
                rule1_min_trailing_silence=float(endpoint.get("rule1_min_trailing_silence", 2.4)),
                rule2_min_trailing_silence=float(endpoint.get("rule2_min_trailing_silence", 1.2)),
                rule3_min_utterance_length=float(endpoint.get("rule3_min_utterance_length", 30.0)),
            )
        elif model_config["pipeline"] == "vad_offline":
            paths = model_config["paths"]
            decode = model_config.get("decode", {})
            sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=paths["model"],
                tokens=paths["tokens"],
                num_threads=int(decode.get("num_threads", 2)),
                use_itn=bool(decode.get("use_itn", False)),
                debug=False,
                hr_rule_fsts=paths.get("hr_rule_fsts", ""),
                hr_lexicon=paths.get("hr_lexicon", ""),
            )
        else:
            raise ValueError(f"Unsupported ASR pipeline: {model_config['pipeline']}")

        result = (True, "")
    except Exception as e:
        result = (False, str(e))

    _VALIDATION_CACHE[cache_key] = result
    return result


def get_model_catalog(path=DEFAULT_CONFIG_PATH, deep=False):
    data = _load_config_data(path)
    active_model = data.get("active_model")
    catalog = []

    for model_id, raw_model in data.get("models", {}).items():
        model = dict(raw_model)
        model["id"] = model_id
        missing = get_missing_files(model)
        loadable, load_error = validate_model_loadable(model, deep=deep)
        catalog.append(
            {
                "id": model_id,
                "display_name": model.get("display_name", model_id),
                "pipeline": model.get("pipeline", ""),
                "installed": len(missing) == 0,
                "loadable": loadable,
                "load_error": load_error,
                "missing_files": missing,
                "active": model_id == active_model and loadable,
                "description": model.get("description", ""),
                "recognizer_kind": model.get("recognizer_kind", ""),
                "language": model.get("decode", {}).get("language", "auto"),
            }
        )

    return catalog


def list_models(path=DEFAULT_CONFIG_PATH, installed_only=False, deep=False):
    models = get_model_catalog(path=path, deep=deep)
    if installed_only:
        models = [model for model in models if model["installed"] and model["loadable"]]
    return models


def list_available_models(path=DEFAULT_CONFIG_PATH, deep=False):
    return list_models(path=path, installed_only=True, deep=deep)


def set_active_model(model_id, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    models = data.get("models", {})
    if model_id not in models:
        raise ValueError(f"Unknown ASR model: {model_id}")
    data["active_model"] = model_id
    _save_config_data(data, path=path)
    
def set_model_language(model_id, language, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    models = data.get("models", {})
    if model_id not in models:
        raise ValueError(f"Unknown ASR model: {model_id}")
    
    decode = models[model_id].get("decode", {})
    decode["language"] = language
    models[model_id]["decode"] = decode
    _save_config_data(data, path=path)

def get_global_languages(path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    return data.get("global_languages", ["zh", "en", "ja", "ko", "yue"])

def set_global_languages(languages, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    data["global_languages"] = list(languages)
    _save_config_data(data, path=path)


def get_history_dir(path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    # Default to ~/Documents/VoxQuill/History if not set
    default_dir = os.path.join(os.path.expanduser("~"), "Documents", "VoxQuill", "History")
    return data.get("history_dir", default_dir)


def set_history_dir(dir_path, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    data["history_dir"] = dir_path
    _save_config_data(data, path=path)


def get_history_enabled(path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    # Default to True
    return data.get("history_enabled", True)


def set_history_enabled(enabled, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    data["history_enabled"] = bool(enabled)
    _save_config_data(data, path=path)


def get_model_download_urls(model_id, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    models = data.get("models", {})
    if model_id not in models:
        raise ValueError(f"Unknown ASR model: {model_id}")
    return [item.get("url", "") for item in models[model_id].get("downloads", [])]


def update_model_download_urls(model_id, urls, path=DEFAULT_CONFIG_PATH):
    data = _load_config_data(path)
    models = data.get("models", {})
    if model_id not in models:
        raise ValueError(f"Unknown ASR model: {model_id}")

    downloads = models[model_id].get("downloads", [])
    if len(urls) != len(downloads):
        raise ValueError("Updated download URL count must match existing downloads")

    for item, url in zip(downloads, urls):
        cleaned = url.strip()
        if not cleaned:
            raise ValueError("Download URL cannot be empty")
        item["url"] = cleaned

    _save_config_data(data, path=path)


def _report_progress(progress_cb, stage, message, value=None):
    if progress_cb:
        progress_cb(stage, message, value)


def _download_file(item, base_dir=MODELS_DIR, progress_cb=None):
    dest_folder = _download_dest(item, base_dir)
    os.makedirs(dest_folder, exist_ok=True)

    filename = _download_filename(item)
    file_path = os.path.join(dest_folder, filename)
    if os.path.exists(file_path):
        _report_progress(progress_cb, "download", f"{filename} already exists", 100)
        return file_path

    _report_progress(progress_cb, "download", f"Downloading {filename}", 0)
    response = requests.get(item["url"], stream=True, timeout=60)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    tmp_path = f"{file_path}.part"

    with open(tmp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            downloaded += len(chunk)
            percent = None
            if total_size > 0:
                percent = int(downloaded * 100 / total_size)
            _report_progress(progress_cb, "download", f"Downloading {filename}", percent)

    os.replace(tmp_path, file_path)
    _report_progress(progress_cb, "download", f"Downloaded {filename}", 100)
    return file_path


def _extract_if_archive(file_path, dest_folder, progress_cb=None):
    if not file_path.endswith(".tar.bz2"):
        return
    _report_progress(progress_cb, "extract", f"Extracting {os.path.basename(file_path)}", None)
    with tarfile.open(file_path, "r:bz2") as tar:
        tar.extractall(path=dest_folder)
    _report_progress(progress_cb, "extract", f"Extracted {os.path.basename(file_path)}", 100)


def ensure_model_ready(model_config, base_dir=MODELS_DIR, progress_cb=None):
    if is_model_ready(model_config):
        return False

    downloads = model_config.get("downloads", [])
    if not downloads:
        missing = ", ".join(get_missing_files(model_config))
        raise FileNotFoundError(
            f"Model '{model_config['id']}' is missing files and has no download metadata: {missing}"
        )

    os.makedirs(base_dir, exist_ok=True)
    for item in downloads:
        file_path = _download_file(item, base_dir=base_dir, progress_cb=progress_cb)
        if item.get("extract", False):
            _extract_if_archive(file_path, _download_dest(item, base_dir), progress_cb=progress_cb)

    missing = get_missing_files(model_config)
    if missing:
        raise FileNotFoundError(
            f"Model '{model_config['id']}' is still missing files after download: {', '.join(missing)}"
        )

    return True


def download_model(model_id, path=DEFAULT_CONFIG_PATH, base_dir=MODELS_DIR, progress_cb=None):
    model_config = load_asr_config(path=path, model_id=model_id)
    changed = ensure_model_ready(model_config, base_dir=base_dir, progress_cb=progress_cb)
    _report_progress(progress_cb, "done", f"Model '{model_config['display_name']}' is ready", 100)
    return changed


def delete_model(model_id, path=DEFAULT_CONFIG_PATH, base_dir=MODELS_DIR):
    data = _load_config_data(path)
    models = data.get("models", {})
    if model_id not in models:
        raise ValueError(f"Unknown ASR model: {model_id}")

    target = dict(models[model_id])
    target["id"] = model_id

    other_required = set()
    other_artifacts = set()
    for other_id, other_raw in models.items():
        if other_id == model_id:
            continue
        other = dict(other_raw)
        other["id"] = other_id
        if is_model_ready(other):
            other_required.update(_iter_required_files(other))
            other_artifacts.update(_iter_downloaded_artifacts(other, base_dir=base_dir))

    removed_paths = []
    for file_path in sorted(set(_iter_required_files(target)), key=len, reverse=True):
        if file_path in other_required:
            continue
        if os.path.isfile(file_path):
            os.remove(file_path)
            removed_paths.append(file_path)

    for artifact_path in sorted(set(_iter_downloaded_artifacts(target, base_dir=base_dir)), key=len, reverse=True):
        if artifact_path in other_artifacts:
            continue
        if os.path.isfile(artifact_path):
            os.remove(artifact_path)
            removed_paths.append(artifact_path)

    for dir_path in _iter_model_dirs(target):
        abs_dir = os.path.abspath(dir_path)
        abs_base = os.path.abspath(base_dir)
        if not abs_dir.startswith(abs_base):
            continue
        if not os.path.isdir(abs_dir):
            continue
        if os.listdir(abs_dir):
            continue
        shutil.rmtree(abs_dir)

    if data.get("active_model") == model_id:
        installed = [model["id"] for model in list_available_models(path=path) if model["id"] != model_id]
        if installed:
            data["active_model"] = installed[0]
            _save_config_data(data, path=path)

    return removed_paths
