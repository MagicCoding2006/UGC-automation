# Sources and third-party components

Checked during implementation on 2026-11-23. These are primary upstream references and provider documentation, not copied project code or an endorsement of unchanged future pricing.

## Model and deployment choices

| Component | Reference | Why it is used |
| --- | --- | --- |
| ComfyUI Wan 2.2 guide | https://docs.comfy.org/tutorials/video/wan/wan2_2 | Native 5B workflow, memory offloading, official model filenames |
| ComfyUI source | https://github.com/Comfy-Org/ComfyUI | Core API node contracts; GPL-3.0 dependency in its own container |
| Wan repackaged models | https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged | 5B, VAE and FP8 encoder weights; pinned revision |
| Wan upstream | https://github.com/Wan-Video/Wan2.2 | Model family and Apache-2.0 licensing |
| Kokoro code | https://github.com/hexgrad/kokoro | Lightweight synthetic speech, Apache-2.0 |
| Kokoro weights | https://huggingface.co/hexgrad/Kokoro-82M | Synthetic voices and model card |
| Hosted Kokoro schema | https://fal.ai/models/fal-ai/kokoro/american-english/api | Prompt, voice, speed and audio result mapping |
| Hosted portrait schema | https://fal.ai/models/fal-ai/flux/schnell/api | Original fictional portrait input/output mapping |
| FLUX schnell model | https://huggingface.co/black-forest-labs/FLUX.1-schnell | Apache-2.0 model card; used through provider |
| Fabric schema | https://fal.ai/models/veed/fabric-1.0/api | Image/audio-driven talking video input/output and resolution tiers |
| Fabric pricing | https://fal.ai/models/veed/fabric-1.0 | $0.08/s 480p and $0.15/s 720p baseline; provider commercial terms |
| InfiniteTalk | https://github.com/MeiGen-AI/InfiniteTalk | Dedicated speech-driven portrait worker, Apache-2.0 model release |
| InfiniteTalk model | https://huggingface.co/MeiGen-AI/InfiniteTalk | Single-person audio-conditioning checkpoint |
| Wan 2.1 base | https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P | Upstream InfiniteTalk base model dependency |
| Wav2vec base | https://huggingface.co/TencentGameMate/chinese-wav2vec2-base | Upstream InfiniteTalk audio encoder; retain its model license |
| RunPod job operations | https://docs.runpod.io/serverless/endpoints/send-requests | Async queue transport, persistent job ID/status polling |
| RunPod source docs | https://github.com/runpod/docs/blob/main/serverless/endpoints/operation-reference.mdx | Current operation examples and timing fields |
| RunPod worker guide | https://docs.runpod.io/serverless/workers/overview | Container worker and cold-start/storage tradeoffs |

The old `fal-ai/infinitalk` page was marked **deprecated / no longer supported** when checked: https://fal.ai/models/fal-ai/infinitalk/api. It is intentionally not a production endpoint in this app. The local worker uses the separate upstream repository.

## Pinned source/model revisions

- ComfyUI: `72212fef660bcd7d9702fa52011d089c027a64d8` (v0.3.59, native Wan 5B support; its SaveVideo node schema matches the included workflow)
- Wan 2.2 repackaged weights: `5df3a4a3ed0628002308022198249dbbbd045d09`
- InfiniteTalk source: `50aa0a94184315407a991ae804d9b58d6d311ba8`
- Wan 2.1 I2V base: `6b73f84e66371cdfe870c72acd6826e1d61cf279`
- InfiniteTalk weights: `d59847ebdacf19245bfca3fb23311c0cada8378a`
- Wav2vec base: `3991242c806928916fff4a8c0e4f76acf661b743`; safetensors override from the upstream-recommended `refs/pr/1` (a mutable PR ref; pin/freeze the resulting image for production).

See Dockerfiles and download scripts for exact dependencies. Core control dependencies and frontend packages are version-pinned; `package-lock.json` records the frontend resolution. GPU upstream requirements include transitive dependency ranges, so freeze an image digest after validating it on real hardware. GPU images have not been built or benchmarked in the implementation environment.

## Application dependencies and attribution

The original control-plane/frontend/worker-wrapper code and repository skills are MIT-licensed under `LICENSE`. They use React, Vite, Lucide, FastAPI, Pydantic, httpx, Pillow and other packages under their respective licenses. FFmpeg is invoked as a separate executable; builds with libx264/libass can carry GPL obligations. ComfyUI remains a separate GPL-licensed container dependency. Preserve upstream notices when distributing images or weights and review the exact dependency licenses in your deployment.

The visual layout is original. Fonts optionally load DM Sans and Manrope through Google Fonts, with local system fallbacks when offline; those fonts use the SIL Open Font License. The project contains no downloaded creator videos, real-person reference portraits, cloned voices, copied brand assets, or vendored third-party skill collections. Model outputs and commercial provider usage remain subject to their applicable terms and rights.

The project-specific skills in `skills/` were authored for this pipeline. They avoid adding external agent instructions or dependencies that the runtime does not need.
