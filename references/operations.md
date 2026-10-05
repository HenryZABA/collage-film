# 工具与可移植运行

所有相对资源从当前 Skill 文件夹解析。不要把素材放到 Skill 目录。

## 依赖与检查

```bash
python3 "$SKILL_DIR/scripts/make.py" --doctor
```

需要 Python 3（Pillow、NumPy）、Node、npm/npx、FFmpeg/ffprobe。本机自动抠图已测 macOS 26.4、Apple Vision，macOS 14+ API 可用性运行时检查。Windows/Linux 可显式配置 rembg 后端，见 cutout.md；未提供跨平台质量保证。HyperFrames 项目固定 CLI 版本，并将 GSAP 拷入项目；第一次执行 npx 可能下载该版本。图片、音乐、前端脚本运行时均为本地资源。

新 Python 环境建议独立 venv 安装：`python3 -m venv .venv`，再用该环境的 pip 安装 `Pillow numpy`。原生 Vision 使用系统 Swift。不要改用户全局包。

## 自动生成一条视频

先收集用户平台/比例和音乐选择。示例路径仅作说明：

```bash
python3 "$SKILL_DIR/scripts/make.py" \
  --images /path/01.jpg /path/02.jpg /path/03.jpg \
  --platform instagram --ratio 9:16 \
  --output /path/my-film \
  --music /path/my-song.wav \
  --pace reference --bpm 100 --lead-in 0.2 --grade warm-film --check
```

- `--images` 顺序就是顺序，2–60张。图像 EXIF 方向归一化后同时交给抠图和视频，原文件不改。
- `--music FILE`、`--demo-music`、`--silent` 必选其一，工具不会自行联网取得音乐。
- `--demo-music` 生成原创简易合成器/节拍 WAV，可用于测试；不是商业库配乐，不与原片音乐相同。
- `--pace reference` 默认每图一拍；100 BPM 时每张0.6秒。`--pace breathing` 以一拍、两拍交替，100 BPM 时为0.6、1.2、0.6、1.2秒。修改 `--bpm` 会实际改变这两种预设的时长；BPM 是用户已知的恒定拍速，没有自动检测任意音乐节拍。
- `--seconds-per-photo 0.75` 覆盖 pace，所有照片均为0.75秒；`--bpm` 不会改变这种显式秒数。`--bpm 100 --beats-per-photo 2` 也覆盖 pace，所有照片均为1.2秒。两个均匀参数互斥，不能同时传。明确按固定秒数、固定拍数剪辑时保留这种模式。
- `--lead-in 0.2` 控制下一张主体提前出现的秒数，默认0.2秒，30 fps 下约6帧；实际值不超过前一张照片时长的一半。第一张没有前图，提前量为0。只改变提前量不会改变整条视频时长。
- 工具接受 BPM 40–240、均匀拍数0.25–32、提前量0–1秒；计算后的每张时长必须满足渲染器0.4–30秒范围。例如200 BPM 的单拍仅0.3秒，会明确拒绝；可显式选择每图两拍。所有数字必须有限，总时长不超过300秒。
- `--skip-cutout 2,4` 指定这些照片做完整照片切换；仅当用户或审片决定这样处理时使用。
- `--text 'Small moments'` 可选居中小字；`--end-title 'Keep exploring'` 可选2秒黑底结尾。
- `--render` 在 check 后生成 `video.mp4`。文件已存在会拒绝；修订 `job.json` 后用 build 重建新输出目录。
- `--fit auto` 根据前景框调整裁切锚点；裁切无法保留完整主体时采用 contain 留边。`--fit cover` 是经视觉确认后的全幅裁切，`--fit contain` 保留完整照片。原图与 mask 始终相同。
- 支持9:16、3:4、4:5、1:1、16:9。Douyin 参数归一化到同竖屏布局建议，上传规范不在此工具承诺内。

产物：inputs/、cutouts/、sources.json、job.json、project/，被要求渲染时有 video.mp4。抠图元数据含源哈希、alpha 面积、bbox、贴边警告。warnings 需要肉眼处理，程序通过不等同审美通过。

四张照片在默认 reference 下只够2.4秒，在 breathing 下只够3.6秒，均不含可选结尾。它们用于检验节奏与转场。更长的成片需要更多新照片；不应为了凑时长把每张延长为数秒。breathing 是可替换的节奏示例，不分析人物或画面复杂度；实际音乐有变速或画面需要不同停留时长时，逐张调整 `job.json` 的 `duration` 和 `leadIn`。`sources.json` 的 `timing` 记录本次模式、实际时长和提前量，`beat_detection` 始终为 false。

## 故事线、主体大小与位置

制作前按 [剪辑脚本](editing-script.md) 写逐镜头计划，并用 `scripts/edit_plan.py` 执行。`make.py --edit-script FILE` 也可直接使用，脚本拥有顺序、拍数和BPM；不与 `--pace` 或均匀时长参数同时使用。

`job.json` 每张可增加 `framing: {"zoom":1.2,"x":0.02,"y":-0.01}`。zoom是整幅画面的倍率，x/y是相对画幅宽高的位移；照片与抠图共用同样参数。cover模式不允许移位露出空边。最终还是需要看主体完整性和实际清晰度。

## 编辑与重新构建

```bash
node "$SKILL_DIR/scripts/build.mjs" --config /path/my-film/job.json --out /path/my-film/revision-02
```

`job.json` 核心结构：

```json
{
  "schemaVersion": 1,
  "title": "Small moments",
  "style": "cutout-reveal",
  "platform": "instagram",
  "ratio": "9:16",
  "grade": "warm-film",
  "fps": 30,
  "scenes": [
    {"duration":0.6,"photo":"inputs/01.png","cutout":"cutouts/01.png","leadIn":0,"position":{"x":0.5,"y":0.5}},
    {"duration":0.6,"photo":"inputs/02.png","cutout":"cutouts/02.png","leadIn":0.2,"position":{"x":0.5,"y":0.5}}
  ],
  "bgm":{"path":"inputs/music.wav","volume":0.45,"fadeIn":0.1,"fadeOut":0.5}
}
```

照片无合适前景时可以不带 `cutout`。路径相对配置文件，不依赖原机器目录。`fit` 为 cover 或 contain；`position` 是图片裁切锚点的0–1坐标；切画幅时按主体位置重调并检查。照片与 mask 尺寸不匹配、PNG 不含有效透明区域、未知字段等都拒绝。

`style: editorial` 是额外可选的多主体拼贴版，使用 `background` 和 `layers`（path/x/y/width/rotation/motion），仅在用户明确需要贴纸拼贴时选择；参考原片采用 cutout-reveal。

在输出项目目录运行：

```bash
npm run check -- --snapshots
npm run preview -- --background
npm run render -- --quality looks --output ../video.mp4
ffprobe -v error -show_streams -show_format ../video.mp4
```

把真实 Studio 项目 URL 交给用户；不要把源 index.html 当成完整预览。不要后台发布或上传用户照片。

## Fork 与包装

```bash
python3 "$SKILL_DIR/scripts/fork.py" --name my-travel-film --destination "$HOME/.codex/skills/my-travel-film"
```

新文件夹名必须匹配新 Skill 名，目标不得存在。复制 scripts、templates（含 GSAP）、references、agents、assets/preset.json，排除 inputs、renders、node_modules、缓存、密钥。修改新副本的 preset.json 后调用该 Skill 即可。合法 GSAP notice 随 vendor 保存；不打包来自 Instagram 的原视频或样本照片。

节奏预设迁移：旧版 `secondsPerPhoto`、`beatsPerPhoto` 已移除，避免固定秒数吞掉 BPM 的变更。新预设用 `pace: "reference"` 和 `bpm: 100` 算出每张0.6秒，`transitionSeconds: 0.2` 决定默认提前量。需要自定义均匀时长时使用显式 `--seconds-per-photo` 或 `--beats-per-photo`；已有 fork 应迁移这两个旧字段，新脚本不会用它们决定节奏。

检查脚本会采样每个真实的抠图中间帧与背景接管帧，避免统一抽样错过短转场；不会加无关漂移动效来让检查通过。

## 主体识别与质量后端

运行 `python3 scripts/make.py --doctor` 检查 BiRefNet/SAM 2 是否可用；按 [cutout.md](cutout.md) 首次配置。`--backend auto` 优先已配置的 BiRefNet，未配置时的实际降级会记录到 QA。`--backend birefnet` 显式要求质量模型，失败不静默替换。

复杂图由 Agent 看图写 [逐图主体计划](subject-selection.md)，再传 `--subjects subjects.json`。每张可指定 BiRefNet、SAM 2 或 Vision；SAM 2 用真实原图哈希绑定框/点。对象语义由 Agent 判断，SAM 2 接收几何，不是假称自动文字识别。逐图计划及实际模型版本均保存在工程证据中。

```bash
python3 scripts/make.py --images photo1.jpg photo2.jpg photo3.jpg \
  --output my-film --platform instagram --ratio 9:16 \
  --subjects subjects.json --demo-music --pace reference --check
```

默认不会为了抠图质量重画人物或修改原RGB；模型和输入都保留原画布。看完mask再接入视频，任何模型产生非空透明图都不等于通过主体验收。

## SAM 边缘精修

`setup_vitmatte.py` 配置后，SAM 2 的默认 `--refine auto` 会继续精修边缘；普通 BiRefNet 不重复精修。逐图计划可写 `refine: "none"` 保留原 mask，或 `refine: "vitmatte"` 强制要求模型已就绪。`make.py --doctor` 同时报告三个模型状态。输入照片始终保留原 RGB 和尺寸；精修结果仍要看图验收。
