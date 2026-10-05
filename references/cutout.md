# 现成模型抠图与本地部署

## 选择哪个后端

- **BiRefNet：** 自动前景的质量默认。复用作者固定版本的公开模型，不训练自己的分割网络。适合人像、动物、产品、多个共同构成主体的对象；显著性预测仍会漏树、选错前景。完成 setup 后 `auto` 优先使用它。
- **SAM 2.1：** 已确定对象的位置时使用。Agent 看图生成框、正点、负点，由现成 SAM 模型分割；能从同图中挑一只杯子而非全部杯子。语义意图及几何格式见 [subject-selection.md](subject-selection.md)。`subject` 文字是审查记录，并非 SAM 2 的文本提示。
- **ViTMatte：** SAM 2 之后的可选边缘精修。复用 Matte Anything 的 SAM→trimap→ViTMatte 方法，默认5×5核、5轮膨胀/腐蚀产生约10像素不确定边缘；不做新图生成。配置后 SAM 的 `--refine auto` 自动使用，`--refine none` 可保留原对象 mask。
- **Apple Vision：** macOS 14+ 的轻量后备，无独立模型下载。没有配置 BiRefNet 时 auto 才使用它，并在 QA 中记录降级原因。它可能把多个物体当作同一个实例，也可能找不到前景。
- **rembg：** 保留旧的独立可选路径，显式支持 u2net/u2netp/isnet-general-use。它不是本轮质量默认，也不混淆 rembg 的代码许可与各模型权重许可。

## 首次配置

普通调用只运行已配置的本地模型，不暗中安装或下载。首次部署由 Agent 或用户执行对应 setup。所有照片留在本机，模型缓存不进入 Skill 分享包。

```bash
python3 scripts/setup_birefnet.py
python3 scripts/setup_sam2.py
python3 scripts/setup_vitmatte.py
python3 scripts/make.py --doctor
```

BiRefNet 的公开权重约445 MB，加上隔离的 Python 依赖；新机器建议 Python 3.11/3.12。若本机已有匹配的 torch，可显式 `setup_birefnet.py --reuse-installed-torch` 在独立环境中只读复用。SAM 2.1 Tiny F16 权重约79 MB，由固定版本的 sam3.cpp 原生实现运行，setup 会配置构建工具并编译，首次 Metal 内核启动较慢。ViTMatte Small 权重约103 MB，默认复用 BiRefNet 的隔离环境，不全局安装 Python 包。每个 setup 的 `--help` 是当前完整参数。

默认缓存 `~/.cache/collage-film`。可用 `COLLAGE_FILM_CACHE` 指向专用目录，setup 与运行使用同一值。运行配置保存解释器/模型路径，Skill 不写死某个用户的绝对路径。源码、权重固定 revision 与 SHA-256；推理离线且不会自动更新版本。

```bash
python3 scripts/birefnet_backend.py --doctor
python3 scripts/sam2_backend.py --doctor
python3 scripts/vitmatte_backend.py --doctor
python3 scripts/cutout.py photo.jpg --backend birefnet --no-crop --output-dir cutouts
python3 scripts/cutout.py photo.jpg --backend sam2 --selection-file selection.json --no-crop --output-dir selected
```

SAM `--refine auto` 在未配置 ViTMatte 时保留二值 mask 并报告原因；显式 `--refine vitmatte` 缺模型会失败。SAM 后端缺少对象计划或模型时明确报错，不默默改用整图自动分割。Apple 实例选择需显式 `--backend vision --instances 1,2`；ID 仅属于当前图片，并非语义名称或排序。

## 输出和质量

每张输出 PNG、同名 `.cutout.json`，及汇总 `cutouts.json`。记录模型/版本、实际后端、输入哈希、框点提示、画布、alpha 范围与警告。默认独立 cutout 命令仍可紧裁；视频必须 `--no-crop`。make.py 已固定保留原画布，并统一 EXIF、裁切与调色。

所有分割输出只添加 alpha，保留原 RGB；不通过生成式编辑重画脸、衣服或物体。照片和抠图重合时才能无跳动地补背景。新输出不能覆盖原图；同名生成文件只有显式 `--overwrite` 才可替换。

**数值检查不等于视觉正确。** 透明像素、面积、模型自估 IoU 都不能证明选中了目标。必须实际查看原图、棋盘格与深浅背景：多主体是否齐全、杯身是否挖空、杯把孔是否干净、脚尖/细杆是否断裂、发丝是否有灰边。SAM 2 提供对象 mask；不能把二值边缘称为高质量发丝 alpha。BiRefNet 不接受 SAM mask 或 trimap，不能整图再跑它并声称做了受约束精修。

本机实测 ViTMatte 改善了 SAM 咖啡杯的边缘台阶和杯把内的小块残留，仍须检查每张图。棕榈叶间天空若已被 SAM 标成确定前景，窄边界精修不会自动清除，这个样本仍判失败。

本机实测 BiRefNet 修复了白咖啡杯被误抠除；人像、双斑马、小企鹅与草伞样本主体可用。棕榈和拥挤船群仍可能漏选/只选一部分，需要对象提示或明确标记失败。本轮是具体样本验收，不是对任意图片的准确率保证；未把 macOS MPS 测试当成 Windows/Linux 实测。

## 原有补充模式

已有透明 PNG 可用 `--backend alpha`。纯色影棚背景可显式 `--backend chroma --key-color '#00ff00'`；颜色扣除会删掉同色主体，绝不能作为自然照片失败后的自动后备。

rembg 仅在独立环境预先安装、模型缓存已备好时运行；首次下载需要显式 `--backend rembg --allow-model-download`。不自动装到系统 Python。

## 上游与许可

- [BiRefNet 作者仓库](https://github.com/ZhengPeng7/BiRefNet) 与 [固定来源模型卡](https://huggingface.co/ZhengPeng7/BiRefNet)：MIT，实际 revision/hash 在 backend 脚本和 runtime 元数据中。
- [Meta SAM 2](https://github.com/facebookresearch/sam2)：模型与主要代码 Apache-2.0；[sam3.cpp 原生适配](https://github.com/PABannier/sam3.cpp)：MIT。本 Skill 用 SAM 2.1 模型，不声称部署了 SAM 3 文本识别。
- [Matte Anything](https://github.com/hustvl/Matte-Anything)：参考成熟组合方法，MIT；[ViTMatte Small 模型卡](https://huggingface.co/hustvl/vitmatte-small-composition-1k)：Apache-2.0。只在对象 mask 周围预测 alpha，原始 RGB 与全画布位置保留。
- [rembg](https://github.com/danielgatis/rembg) 的代码许可不能代替各权重许可。BRIA RMBG 的非商业权重不作为本工具默认商业使用路线。

Fork 只复制 Skill 的代码、方法、模板与预设；不会复制模型缓存、环境、用户照片、参考帧或登录态。新机器仍需 setup，原机器可以复用经过核验的共享模型缓存。
