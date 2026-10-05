# 生成与影片一致的拼贴封面

用户要求封面时才走此路线，沿用已有平台、画幅、配色和白边选择。无需重新询问或重做影片。封面是精选构图，视频的完整素材覆盖要求不代表每张照片都要塞进封面。

## 参考图与构图

先用 view_image 查看每张本地参考。优先清晰的主角身份照，再选车辆/动物/地貌等不同角色；最多5张参考。更多元素用已有视频转场联系表作为其中一张参考，并明确禁止复制网格、编号、黑条或整张矩形照片。参考质量不足时换图，不能凭空添加未出现的景物、人物或旅行道具。

主角最大、脸无遮挡；山体/悬崖作为宽阔后层，车辆和动物作为中层，花朵/食物作为较小前层。约10–14个可识别元素是丰富度参考，按素材和可读性调整。大小不均、非对称斜向排列、合理遮挡，保留呼吸空间。暖米色背景、统一保守暖色摄影质感；默认不加相框、胶带、整齐贴纸阵列或涂鸦。仅在用户选择白边时加入窄白轮廓，小元素细边、大主体适度加粗，轻微接触阴影。标题可用已知项目名或用户原文；不杜撰口号。

## 生成提示模板

使用当前环境可用的内置 image_gen 工具，遵循 imagegen Skill；无需额外 API Key。所有参考都有本地路径时用 referenced_image_paths；不要同时使用最近图片数量参数。背景不透明。将下面变量替换为看图后确认的具体内容：

```text
Use case: compositing / identity-preserve.
Create ONE finished photographic cutout-collage cover for [platform], exact [ratio], matching the existing video's [palette / grade / outline choice].
Input roles: image 1 = identity and largest portrait; image 2 = [supporting subject]; image 3 = [supporting subject]; image 4 = [landscape]; image 5 = existing transition contact sheet, reference for its individual subjects and visual style ONLY. Never reproduce its grid, labels, bars or complete rectangular photos.
Use only these observed subjects: [explicit inventory]. Compose a dense but readable asymmetric montage with unequal subject sizes, diagonal flow, layered overlaps and breathing space. Keep the main face unobscured and preserve identity, expression, glasses and clothing. Broad landscape silhouettes form back layers, medium subjects form middle layers, small flowers/foods form foreground accents.
Backdrop: [video background]. Photographic source textures and natural candid detail, unified gently with the video's palette. [If selected: narrow WHITE contours proportional to each displayed subject, hairline edges for tiny elements; subtle contact shadows.] No equal tiles, polaroid frames, tape, doodles, invented props or illustration conversion.
Text: [only exact approved heading, or no text]. No other text, logos, watermark or invented slogan. Montage dominates the hierarchy.
Deliver one polished ready-to-use [ratio] cover.
```

这是参考驱动的 AI 拼贴，可能改变局部细节，不等同视频中保留原 RGB 的抠图。用户要求原照片像素与人物严格不变时，明确采用原 PNG 的确定性组装路线；不得用 AI 重生成偷偷替代。

## 验收与保存

生成后看实际图片，检查真实宽高比、主角身份、脸与手、动物完整性、元素可辨认、大小层次、白边比例和文字。不要仅凭提示声称精确尺寸或4K。明显缺陷用一个具体修订再次生成并复查。保存最终提示、参考角色清单、生成方式与验收记录在私人影片输出目录；将工具生成文件复制到该目录后交付可点击本地文件及图片预览。公开 Skill 仅存方法模板，不收录私人照片、联系表、封面或绝对素材路径。
