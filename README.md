# Collage Film

A reusable, forkable Agent Skill that turns photos into subject-first reveal videos. The subject from the next photo appears over the current scene, followed by its full photo in the same position.

The current version plans the story, pacing and framing before building an editable HyperFrames project. It combines local subject segmentation, adaptive white outlines, original tropical music, color grading, native 4K masters, mobile playback exports and optional photographic collage covers.

## Preview

![Preview](examples/travel/story/preview.gif)

## Install

Ask your Agent:

> Install https://github.com/HenryZABA/collage-film as a Skill and complete its local setup.

Or clone it into an empty skill directory:

```bash
git clone https://github.com/HenryZABA/collage-film.git ~/.codex/skills/collage-film
```

A packaged Skill is available in the [latest release](https://github.com/HenryZABA/collage-film/releases/latest).

## Use

> Use $collage-film to turn the photos in this folder into a travel video for Instagram Reels, 9:16. Use my music file. Plan the story and alternate subject sizes before assembling the video.

For selective cutouts:

> Keep only the person holding the camera. Exclude the vehicle and other people.

The Agent asks for missing platform, aspect ratio and music preferences, inspects the photos, and prepares a short editing script. It then reviews the cutouts, builds the project and exports an MP4 when requested. It does not publish to social platforms automatically.

## Workflow

1. **Plan the edit.** Inventory every input and retain full coverage unless the user authorizes curation. Define a story, photo order, each shot's purpose and connection, beat count, subject size and placement. Use wide shots intentionally and alternate them with closer subjects where the story benefits.
2. **Select and isolate subjects.** The Agent inspects each photo. BiRefNet handles automatic foreground extraction; SAM 2.1 uses Agent-authored boxes and points for specific objects, including mountains, cliffs and roads. ViTMatte refines SAM mask edges.
3. **Execute the script.** Apply the planned order, timing, zoom and subject anchors. Report pixel enlargement, cropping and runs of small subjects. Photos and cutouts share the same framing so the background reveal stays aligned.
4. **Assemble and review.** Add music and consistent grading in HyperFrames. Inspect subject detail, transition frames and the final video before delivery.

Story and composition decisions come from the Agent's visual judgment. The tools execute and measure the plan; they do not automatically infer a story or guarantee image quality.

## Features

- Executable editing scripts for story order, per-shot beats, zoom and placement.
- Full-coverage or explicitly curated edits with source hashes and omission checks.
- Local automatic or targeted cutouts, including landscape silhouettes and multiple subjects.
- Optional white contour overlays sized to each displayed subject, without changing source pixels.
- Edge refinement that preserves source RGB and full-canvas alignment.
- Editable HyperFrames projects, native 4K rendering and bounded mobile MP4 exports.
- Reference-driven AI collage covers matching the video, with identity and composition review.
- Aspect ratios: 9:16, 3:4, 4:5, 1:1 and 16:9.
- User-provided music, original procedural preview / tropical guitar and percussion music, or silence.
- Warm-film, cool-editorial or original-color treatment.
- Forkable personal presets for pacing, color and style.

Timing uses a known constant BPM or explicit durations. The reference preset uses one beat per photo; at 100 BPM that is 0.6 seconds, with a 0.2-second subject prelude. Editing scripts can vary these choices shot by shot.

## Local setup

Requires Python with Pillow and NumPy, Node.js, FFmpeg and the segmentation runtimes. Python 3.11 or 3.12 is recommended for a new environment. The native SAM backend on macOS also needs Apple Command Line Tools.

The Agent can run the setup scripts for you:

```bash
python3 scripts/setup_birefnet.py
python3 scripts/setup_sam2.py
python3 scripts/setup_vitmatte.py
python3 scripts/make.py --doctor
```

Setup downloads pinned, hash-verified model files. The three model weights total approximately 627 MB; runtime dependencies require additional space. Models and isolated environments are stored outside the Skill in `~/.cache/collage-film`, configurable with `COLLAGE_FILM_CACHE`. Forks on the same machine can reuse this cache.

Segmentation runs locally without uploading photos. Optional white outlines require OpenCV; tropical music requires SciPy in the active isolated Python environment. AI covers use the host Agent’s built-in image generation tool and send the selected references to that service. Models, environments and user media are not bundled into a fork. See the [backend setup and licenses](references/cutout.md) for details.

## Export and covers

For an original tropical soundtrack, add `--demo-music --music-style tropical-guitar`; use `--white-outline` for proportional borders. Use `--resolution 4k --delivery master --render` for a native master. A 3:4 4K canvas is 2880 × 3840, rebuilt from source assets.

The default rendered delivery retains a master and creates a mobile MP4: up to 1080 on the short edge / 1920 on the long edge, constant 30 fps, H.264 High Level 4.1, 8-bit 4:2:0, bounded 6 Mbps video and AAC audio. This reduces decoding load; playback on every phone is not guaranteed. To convert an existing SDR master:

```bash
python3 scripts/export_mobile.py --input /path/master.mp4 --output /path/mobile.mp4
```

For a cover, ask the Agent to make a photographic montage in the video's ratio and palette. It selects up to five references, arranges a clear main subject with supporting landscape, animal, vehicle and detail layers, then reviews the result. AI covers may alter details; they are separate from the pixel-preserving video cutouts. Private media stays outside the public repository.

## Fork your own version

> Fork $collage-film as my-travel-film and save my preferred pacing and color treatment.

```bash
python3 scripts/fork.py \
  --name my-travel-film \
  --destination ~/.codex/skills/my-travel-film
```

The destination must not already exist. Customize `assets/preset.json` in the new Skill. Photos, music, credentials and model caches are excluded.

## Outputs and documentation

Deliverables include the editing script, framing review, transparent cutouts, source records, `job.json`, an editable HyperFrames project and an MP4 when rendering is requested.

- [Skill workflow](SKILL.md)
- [Editing script format and execution](references/editing-script.md)
- [Tool usage and project format](references/operations.md)
- [Subject selection plans](references/subject-selection.md)
- [Cover generation](references/cover.md)
- [Adaptive outlines, 4K and mobile delivery](references/outline-and-export.md)
- [Original tropical music](references/music.md)

## Limits

Validated on macOS / Apple Silicon for model inference, targeted subject selection, edge refinement, executable editing plans, independent forks and 9:16 / 3:4 video exports. Native 3:4 4K rendering and 30 fps mobile transcoding have also been verified locally. Windows, Linux, CPU-only operation, full-resolution 4K matting and playback on every phone have not been fully validated.

Complex foliage, transparent materials, occlusion and similar foreground/background colors still require visual review. Enlarging a subject cannot recover motion-blurred detail or hidden anatomy; prefer higher-resolution originals, a different crop, a different photo or a deliberate wide shot when appropriate.

A non-empty alpha mask or passing technical check is not visual acceptance. Automatic beat detection for arbitrary songs is not implemented.

## License

Original project code and documentation are licensed under [MIT](LICENSE). GSAP, model weights and upstream implementations retain their own licenses; see [third-party notices](THIRD_PARTY_NOTICES.md). Photo and music rights are separate from the code license.
