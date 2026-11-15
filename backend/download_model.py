#!/usr/bin/env python3
"""
========================================================================================
Dedicated Model Downloader for ServiceLog Intelligence Hub
========================================================================================
Downloads local offline model weights (0.5B, 1.5B, 3B) directly into the models/ folder.
Usage:
    python backend/download_model.py --model 1.5B
    python backend/download_model.py --model 3B
    python backend/download_model.py --model 0.5B
========================================================================================
"""

import sys
import argparse
import time
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REGISTRY = {
    "0.5B": {
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "target_dir": MODELS_DIR / "Qwen2.5-0.5B-Instruct",
        "display_name": "Qwen 2.5 0.5B Instruct",
        "size_est": "~988 MB"
    },
    "1.5B": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "target_dir": MODELS_DIR / "Qwen2.5-1.5B-Instruct",
        "display_name": "Qwen 2.5 1.5B Instruct",
        "size_est": "~3.1 GB"
    },
    "1B": {
        "repo_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "target_dir": MODELS_DIR / "Qwen2.5-1.5B-Instruct",
        "display_name": "Qwen 2.5 1.5B Instruct",
        "size_est": "~3.1 GB"
    },
    "3B": {
        "repo_id": "Qwen/Qwen2.5-3B-Instruct",
        "target_dir": MODELS_DIR / "Qwen2.5-3B-Instruct",
        "display_name": "Qwen 2.5 3B Instruct",
        "size_est": "~6.1 GB"
    }
}


def download_model(model_key: str, force: bool = False) -> bool:
    key_upper = model_key.strip().upper()
    
    # Check if key is known or custom repo ID
    if key_upper in MODEL_REGISTRY:
        info = MODEL_REGISTRY[key_upper]
        repo_id = info["repo_id"]
        target_dir = info["target_dir"]
        display_name = info["display_name"]
        size_est = info["size_est"]
    else:
        # Custom repo ID passed
        repo_id = model_key.strip()
        folder_name = repo_id.split("/")[-1]
        target_dir = MODELS_DIR / folder_name
        display_name = repo_id
        size_est = "Unknown"

    print("\n" + "=" * 80)
    print(f"📥 [MODEL-DOWNLOAD] Downloading: {display_name}")
    print(f"• Hugging Face Repository : {repo_id}")
    print(f"• Local Destination Folder: {target_dir}")
    print(f"• Estimated Download Size : {size_est}")
    print("=" * 80 + "\n")

    # Check if already downloaded
    if not force and target_dir.exists():
        has_config = (target_dir / "config.json").exists()
        has_weights = any(target_dir.glob("*.safetensors")) or any(target_dir.glob("*.bin"))
        if has_config and has_weights:
            print(f"✅ [ALREADY-EXISTS] Model files already exist in: {target_dir}")
            print("   (Pass --force if you want to re-download or update weights.)\n")
            return True

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("❌ [ERROR] huggingface_hub package is required. Install via pip install huggingface-hub")
        return False

    start_time = time.time()
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        print(f"🚀 Downloading files from Hugging Face Hub (this may take a few minutes depending on network speed)...")
        
        downloaded_path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(target_dir),
            local_dir_use_symlinks=False
        )

        duration = round(time.time() - start_time, 2)
        print("\n" + "=" * 80)
        print(f"🎉 [DOWNLOAD-COMPLETE] Successfully downloaded {display_name} in {duration}s!")
        print(f"• Location: {downloaded_path}")
        print("=" * 80 + "\n")
        return True

    except Exception as e:
        print(f"\n❌ [DOWNLOAD-FAILED] Error downloading {repo_id}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download Qwen SLM models for offline inference")
    parser.add_argument("--model", type=str, default="1.5B", help="Model to download (0.5B, 1.5B, 3B, or Hugging Face repo ID)")
    parser.add_argument("--force", action="store_true", help="Force re-download even if folder exists")
    args = parser.parse_args()

    success = download_model(args.model, force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
