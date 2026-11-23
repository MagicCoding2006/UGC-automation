from pathlib import Path
from huggingface_hub import hf_hub_download

root = Path('/opt/ComfyUI/models')
repo = 'Comfy-Org/Wan_2.2_ComfyUI_Repackaged'
revision = '5df3a4a3ed0628002308022198249dbbbd045d09'
for subdir, name in [('diffusion_models','wan2.2_ti2v_5B_fp16.safetensors'),
                     ('text_encoders','umt5_xxl_fp8_e4m3fn_scaled.safetensors'),
                     ('vae','wan2.2_vae.safetensors')]:
    destination = root/subdir/name
    if destination.exists():
        continue
    source = hf_hub_download(repo, 'split_files/'+subdir+'/'+name, revision=revision)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Move to the persistent model volume, avoiding a second permanent copy.
    import shutil
    shutil.copyfile(source,destination.with_suffix('.part'))
    destination.with_suffix('.part').replace(destination)
    print('Ready:',name,flush=True)
