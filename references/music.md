# 原创热带配乐

沿用用户的音乐选择。`--demo-music` 默认简易 preview；用户要轻松热带感、吉他与打击乐时：

```bash
python3 "$SKILL_DIR/scripts/music.py" --style tropical-guitar --duration 18 --bpm 100 --output /path/original-music.wav
```

make 接口为 `--demo-music --music-style tropical-guitar`。可选依赖 SciPy 安装到当前独立 Python 环境。音色为物理拨弦合成的尼龙吉他风格，配低音、康加鼓、沙锤和木块；不是现场吉他录音、商业曲库或参考原片同款。没有采样歌曲。生成器按最终时长安排小节、收束和淡出，不把过短音乐粗暴循环。music.json 记录来源、乐器、BPM、时长、采样率与峰值。

先执行剪辑脚本再按其BPM/总时长生成配乐。已知恒定节奏才使用拍数网格；工具不检测任意歌曲拍点。听头尾、转场、乐器平衡，检查无削波、无断音和音频流实际存在。用户提供的曲目保持其权利与来源记录。
