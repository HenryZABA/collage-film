---
name: collage-film
description: 把用户照片制作成 Muse 风格的主体抠图转场视频，自动分离前景、衔接全幅照片、适配发布平台和比例、添加 BGM 与统一调色，并生成可编辑 HyperFrames 项目。支持 fork 成用户自己的风格 Skill。适用于旅行、生活方式、人物和产品照片的动态拼贴，不用于持续运动视频的逐帧抠像。
---
# Collage Film

把一组照片变成「下一张主体先叠入 → 同位置补上下一张完整照片」的视频。默认不加纸片边框、贴纸阴影或大标题；原帖参考与时间结构见 [references/style.md](references/style.md)。本 Skill 带可运行工具，并非只给提示词。

## 先问缺失的两个关键选择

自然询问：**准备发在哪个平台？想要什么比例？** 可以一起提供选项。若用户已说明则直接沿用；不能把平台推测当成用户选择。

- Instagram Reels／TikTok／抖音／YouTube Shorts：推荐 9:16。
- 小红书：推荐 3:4 或 9:16；Instagram Feed：4:5 或 1:1。
- 横屏 YouTube／网页：16:9。

以上是构图建议，不承诺平台最新上传限制。若用户要求精确平台规范，先查平台官方当前规则。

然后确认照片位置、排序、时长与音乐偏好。用户只给参考链接时，先查看参考，再索取其自己的照片；可先完成工具或风格配置，不把参考视频帧伪称用户原图。问题尽量合并，只问影响成片的缺失信息。创作需要照片输入，平台和比例不是抠图效果的替代信息。

## 运行

`SKILL_DIR` 表示当前 SKILL.md 所在目录；从文件实际位置解析，不能假定 fork 后名称不变。先查看脚本 `--help` 与 [references/operations.md](references/operations.md)。Node、Python 3、Pillow/NumPy、FFmpeg 和 HyperFrames 是运行依赖。抠图复用成熟模型：BiRefNet 自动前景，SAM 2 指定对象、ViTMatte 精修边缘，Apple Vision 作为轻量后备；按 [references/cutout.md](references/cutout.md) 检查和配置，不把此机成功等同跨平台验证。

1. **看图确定主体。** 保留用户原片，检查 EXIF 后的画面及出框情况。逐张看图，用一句话记录要保留的对象与要排除的干扰；不能把“最大连通区域”“全部人物”当成主体判断。多主体如两只杯子、两只斑马可共同构成主体。背景纷杂或只选其中一个对象时，由 Agent 根据实际画面生成框/包含点/排除点，写入 `--subjects` 计划；通常无需用户手动画框。主体含义确实无法判断时再问一句。格式见 [references/subject-selection.md](references/subject-selection.md)。
2. **分割与复查。** 已配置时 `scripts/cutout.py --backend auto` 优先 BiRefNet；需要指定对象时用 SAM 2 与逐图计划；配置 ViTMatte 后默认将对象 mask 转成 trimap，再精修边缘。使用 `--no-crop` 保留全画布，只改变 alpha，不重画主体。读取 `cutouts.json`，把抠图叠在棋盘格和纯色背景上检查对象完整性、发丝、手指、杯把孔及背景残留；数值 QA 通过不等于主体正确。漏选或选错就修正对象提示重新分割；仍失败要明确标出，不能以生成了透明 PNG 冒充成功。SAM 的对象 mask 不等于精细发丝 alpha；ViTMatte 也不能修复被错误标成确定前景的背景区域。树叶间的天空、透明玻璃等必须检查。BiRefNet 不是可消费 SAM 提示的精修器，不能盲目求并/求交。
3. **组合。** 用 `scripts/make.py` 编排和构建，或手工写 `job.json` 后调用 `node scripts/build.mjs --config job.json --out project`。前景 PNG 与原图必须同一尺寸、同一裁切位置；同一主体先出现再揭示背景。默认 `--pace reference` 每图一拍，100 BPM 时每图0.6秒；`--pace breathing` 按一拍、两拍交替，为0.6、1.2秒。抠图默认提前0.2秒，且不超过前一张时长的一半。四张图分别只够2.4秒或3.6秒短样；做长片应补充新的照片，不能把每张拖长来冒充参考密度。复杂画面按具体照片手调 `job.json`，breathing 只是节奏预设，不是自动识别人像或画面复杂度。
4. **配乐。** 优先用户指定且可使用的音乐；可通过已配置的 `media-use` 搜索/生成。工具附带 `music.py` 可生成原创的简易预览节奏，不应称为原片同款音乐或商业音乐库。未提供音乐且未选默认时先问；用户明确要无音乐就尊重。BPM 网格仅适用于已知恒定节拍；不把任意歌曲假称自动踩点。
5. **调色。** 默认 `warm-film` 是参考方向的保守版本，也支持 `none`、`cool-editorial`；由 HyperFrames 原生 `data-color-grading` 处理，主体与对应整图同一参数。品牌色/肤色保真时先用 `none`。用前后画面检查，HDR/LOG 输入先正确转 SDR；不可硬套滤镜。
6. **检查并交付。** 读可用的 `hyperframes`、`hyperframes-core` 和 `hyperframes-cli` 技能；用 `check --snapshots` 检查，并审视转场中间帧与头尾。打开 Studio。若用户已授权成片/一口气完成则继续渲染；否则根据用户要求的协作方式展示预览。检查输出尺寸、时长、视频/音频流及 mask；不自动发布到社交平台。

## Fork

用户说「fork 这个 Skill」时，复制方法、预设与工具；用户照片、音乐和产物保持在项目外。

```bash
python3 "$SKILL_DIR/scripts/fork.py" --name my-travel-film --destination "$HOME/.codex/skills/my-travel-film"
```

拒绝覆盖现有目录。修改新副本的 `assets/preset.json` 即可保存自己的色调、节奏、文本和默认动效。新 Skill 的元数据与调用名称自动改名。不要把 API key、登录态、素材或用户原片打进分享包。

## 交付契约

交付 MP4（被要求渲染时）、可编辑 HyperFrames 文件夹、`job.json`、透明 PNG 与抠图 QA、素材/音乐来源说明。给出真正可打开的文件或 Studio 链接。报告已验证的平台比例和抠图后端；未经实测不声称跨平台、自动识别所有物体或精确复刻音乐节拍。
