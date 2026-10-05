# 自适应白边、原生4K与手机交付

## 白边

做白边A/B实验时复用同一剪辑脚本、mask、配乐、调色与编码，仅改变 outline.enabled；不同时改变镜头节奏或素材。默认不加，用户选择后用 `make.py --white-outline`，或 job 根字段：

```json
{"outline":{"enabled":true,"radiusRatio":0.012,"maxRadiusFraction":0.0111111111}}
```

build 调用 outline.py 从 alpha 生成独立白色 SVG 轮廓，不修改原图 RGB 或 alpha。安装可选 `opencv-python-headless` 到当前独立 Python 环境；手工运行 Node 时通过 `COLLAGE_FILM_PYTHON` 指定该环境，make 自动沿用自己的 Python。

边缘半径为最终显示主体 bbox 较短边的1.2%，上限为画幅短边的1/90（1080画幅为12px，2880画幅为32px），没有强制最小厚度。多个独立花朵/火焰等可在该 scene 设置 `outlinePerComponent:true`；同一主体被遮挡分成碎片时保持默认整组尺度。内部孔洞也有轮廓。极小轮廓只略过其白边，不删除主体。

轮廓与 PNG 共用 fit、position、zoom、位移、提前时间与时长，位于主体下层；白边不调色。完整照片接管时白边消失。检查小元素边缘、遮挡处、孔洞，以及接管前后有没有跳位。支持 cutout-reveal；editorial 多层边框尚未接入。`outline-report.json` 保存实际半径与时序。

## 原生4K

`make.py --resolution 4k --delivery master --render`；手工 job 设置 `resolution:"4k"` 后从源照片与 SVG 重新 build/render。3:4 是2880×3840，9:16 是2160×3840，16:9 是3840×2160。构图坐标保持比例，标题与位移按画幅缩放。不要将旧1080视频放大并称作原生4K。高分辨率输出不能恢复原片模糊或遮挡，仍须检查画质倍率与细节。

## 手机播放版

渲染器输出可能采用过高编码等级、峰值码率或尺寸；30fps 本身不能证明播放流畅。手机卡顿/漏画面时先查 ffprobe 的实际编码、profile/level、像素格式、分辨率、帧率、码率和帧数，再核对连续时间戳及全部转场，区分文件缺帧与设备解码压力。不要未经检查就延长镜头或改故事节奏。

make 默认 `--delivery mobile`：保留 video-master.mp4，并生成 video.mp4。独立转换：

```bash
python3 "$SKILL_DIR/scripts/export_mobile.py" --input /path/video-master.mp4 --output /path/video-mobile.mp4
```

手机预设：保持比例，短边≤1080、长边≤1920、恒定30fps、H.264 High Level4.1、8-bit yuv420p、6Mbps最大码率/12Mbps缓冲、2秒关键帧、AAC立体声48kHz、MP4 faststart。HDR先正确转SDR，工具拒绝将PQ/HLG直接改标签。母版留存；手机转码不称4K。明确要求4K母版时沿用用户选择，同时可提供手机副本。

工具检查完整解码帧数与连续时间戳并保存 export.json。交付前还要看实际解码的每张整图、所有短抠图中间帧和头尾，并核对素材哈希/序号覆盖。源为30fps时核对所有540帧等应有帧数；其他源帧率转换允许正常重采样，不能承诺逐帧不变。未在用户手机试播，不宣称所有设备已验证。默认本地保存并给可点击文件；仅有明确云端需求才上传。
