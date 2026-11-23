from huggingface_hub import snapshot_download, hf_hub_download
from pathlib import Path
root = Path('/models')
for repo, name, revision, patterns in [
    ('Wan-AI/Wan2.1-I2V-14B-480P','Wan2.1-I2V-14B-480P','6b73f84e66371cdfe870c72acd6826e1d61cf279', None),
    ('TencentGameMate/chinese-wav2vec2-base','chinese-wav2vec2-base','3991242c806928916fff4a8c0e4f76acf661b743',None),
    ('MeiGen-AI/InfiniteTalk','InfiniteTalk','d59847ebdacf19245bfca3fb23311c0cada8378a',['single/*','LICENSE*','README.md']),
]:
    snapshot_download(repo, revision=revision, local_dir=root/name, allow_patterns=patterns,
        ignore_patterns=['*.mp4','*.jpg','*.png','*.gif','*.pth'] if name!='Wan2.1-I2V-14B-480P' else None)
# Official upstream setup provides a safetensors audio encoder in this revision.
hf_hub_download('TencentGameMate/chinese-wav2vec2-base','model.safetensors',revision='refs/pr/1',local_dir=root/'chinese-wav2vec2-base')
