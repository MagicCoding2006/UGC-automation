import json
import math
import shutil
import textwrap
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from . import config
from .creative import caption_chunks, caption_text
from .providers import duration, probe, run


def font(size):
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def card(path, product, creator, hook, demo=False):
    im = Image.new('RGB', (720, 1280), '#131820')
    d = ImageDraw.Draw(im)
    color = product.get('color', '#b8f36b')
    d.rounded_rectangle((30, 30, 690, 1250), 36, fill='#202936')
    d.text((65, 55), 'STUDIO / ' + ('PIPELINE PREVIEW' if demo else 'PRODUCT STORY'), font=font(20), fill=color)
    y = 205
    title_lines = textwrap.wrap(product['name'], 18)
    title_size = min(51,max(24,int(185/max(1,len(title_lines))*.85)))
    for line in title_lines:
        d.text((65, y), line, font=font(title_size), fill='white')
        y += int(title_size*1.25)
    # An original geometric product mark; never pass this off as a product photo.
    d.ellipse((170, 430, 550, 810), fill=color)
    d.rounded_rectangle((295, 475, 425, 740), 30, fill='#26303d')
    d.rounded_rectangle((322, 450, 398, 495), 12, fill='#26303d')
    d.line((320, 540, 320, 675), fill='#ffffff', width=5)
    if demo:
        d.text((65, 1110), 'TEST FOOTAGE', font=font(24), fill=color)
        d.text((65, 1150), 'Not a generated person or real product demo', font=font(17), fill='#c8d0d8')
    im.save(path)


def ass_time(seconds):
    cs = round(seconds * 100)
    return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'


def subtitles(path, script, seconds, width, height, style):
    size = round(width * (.058 if style == 'bold' else .045))
    cues = caption_chunks(script['text'], seconds)
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size},&H00FFFFFF,&H000000FF,&H00202020,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,65,65,{round(height*.22)},1
Style: Disclosure,DejaVu Sans,{round(width*.024)},&H00FFFFFF,&H000000FF,&H00202020,&H90000000,0,0,0,0,100,100,0,0,1,1,0,8,35,35,{round(height*.08)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = [f'Dialogue: 0,{ass_time(c["start"])},{ass_time(c["end"])},Default,,0,0,0,,{caption_text(c["text"])}' for c in cues]
    lines.append(f'Dialogue: 1,0:00:00.00,{ass_time(seconds)},Disclosure,,0,0,0,,AI-GENERATED {" / DEMO" if script.get("demo") else ""}')
    path.write_text(header + '\n'.join(lines), encoding='utf-8')
    srt = path.with_suffix('.srt')
    def stamp(v):
        ms = round(v*1000)
        return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    srt.write_text('\n\n'.join(f'{i+1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{c["text"]}' for i,c in enumerate(cues))+'\n')
    return cues


def render(job, script, audio, footage, assets):
    """Normalize clips before concat: bounded RAM and reliable mixed input types."""
    directory = config.MEDIA / job['id']
    directory.mkdir(exist_ok=True)
    seconds = duration(audio) + .25
    width = config.RESOLUTION
    height = round(width * 16 / 9 / 2) * 2
    if width not in (360, 480, 720, 1080):
        raise ValueError('UGC_RENDER_RESOLUTION must be 360, 480, 720 or 1080')
    sources = []
    rng = random.Random(job['spec']['seed'])
    assets = list(assets)
    rng.shuffle(assets)
    if footage:
        # Preserve audio alignment when returning to the avatar after B-roll.
        if assets:
            sources = [(footage, seconds*.45, 0), (config.MEDIA/assets[0]['path'], seconds*.35, 0), (footage, seconds*.2, seconds*.8)]
        else:
            sources = [(footage, seconds, 0)]
    elif assets:
        sources = [(config.MEDIA/a['path'], seconds/len(assets), 0) for a in assets]
    else:
        image = directory / 'preview.png'
        card(image, job['spec']['product'], job['spec']['creator'], script['hook'], script.get('demo', False))
        sources = [(image, seconds, 0)]
    pieces = []
    for i, (source, length, offset) in enumerate(sources):
        still = source.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
        piece = directory / f'shot-{i}.mp4'
        if not footage and not still:
            source_duration = duration(source)
            offset = rng.uniform(0, max(0, source_duration-min(length,3)))
        inputs = ['-loop', '1', '-i', source] if still else ['-stream_loop', '-1', '-ss', str(offset), '-i', source]
        filters = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30'
        if still:
            # Slow, seeded pan/zoom creates fresh edits without new GPU inference.
            direction = rng.choice(('in','out'))
            step = rng.uniform(.00004,.00010)
            zoom = f'min(1.04,1+on*{step:.7f})' if direction=='in' else f'max(1,1.04-on*{step:.7f})'
            filters += f",zoompan=z='{zoom}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps=30"
        run(['ffmpeg', '-y', '-v', 'error', *inputs, '-t', f'{length:.3f}', '-vf', filters,
             '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-threads', '2', piece], 600)
        pieces.append(piece)
    concat = directory / 'concat.txt'
    # All names are generated internally; never interpolate user-controlled file names here.
    concat.write_text(''.join(f"file '{p.name}'\n" for p in pieces))
    ass = directory / 'captions.ass'
    cues = subtitles(ass, script, seconds, width, height, job['spec']['caption_style'])
    final = directory / 'final.mp4'
    # Relative subtitle name avoids Windows drive-letter and escaping issues.
    import subprocess
    command = ['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '1', '-i', 'concat.txt', '-i', str(audio),
        '-vf', 'ass=captions.ass', '-af', 'apad,loudnorm=I=-16:TP=-1.5:LRA=11', '-t', f'{seconds:.3f}',
        '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-threads', '2', 'final.mp4']
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=900)
    if result.returncode:
        raise RuntimeError(result.stderr[-2400:])
    poster = directory / 'poster.jpg'
    run(['ffmpeg', '-y', '-v', 'error', '-ss', '0.5', '-i', final, '-frames:v', '1', poster])
    for piece in pieces:
        piece.unlink(missing_ok=True)
    return dict(video=str(final.relative_to(config.MEDIA)), poster=str(poster.relative_to(config.MEDIA)),
        subtitles=str(ass.with_suffix('.srt').relative_to(config.MEDIA)), duration=seconds,
        caption_alignment='Estimated from script length; check timing during review', cues=cues)


def technical_qa(path, expected_seconds):
    info = probe(path)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), {})
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), {})
    seconds = float(info['format']['duration'])
    checks = dict(video_present=bool(video), audio_present=bool(audio),
        portrait=abs(video.get('width', 0)/max(video.get('height', 1), 1)-9/16) < .01,
        duration=abs(seconds-expected_seconds) < .75,
        h264=video.get('codec_name') == 'h264', aac=audio.get('codec_name') == 'aac',
        file_size=path.stat().st_size > 15000)
    # Full decode catches broken packets, not only a readable container header.
    run(['ffmpeg', '-v', 'error', '-i', path, '-f', 'null', '-'], 600)
    checks['decodes'] = True
    return dict(passed=all(checks.values()), checks=checks, duration=seconds,
        requires_human=['realism', 'lip-sync', 'product accuracy', 'caption timing', 'claim context'],
        visual_model_score=None)
