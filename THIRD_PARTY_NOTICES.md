# Third-party notices

The root MIT license covers original Collage Film code and documentation only.

- **GSAP 3.14.2:** `templates/vendor/gsap.min.js` retains its original notice and is governed by the [GSAP Standard License](https://gsap.com/standard-license), not this project's MIT license. See `templates/vendor/GSAP-LICENSE.txt`.
- **BiRefNet:** [author repository](https://github.com/ZhengPeng7/BiRefNet) and [model](https://huggingface.co/ZhengPeng7/BiRefNet), MIT. Setup downloads pinned, verified source/model files to an external cache. The model is not included in this repository.
- **SAM 2.1:** [Meta SAM 2](https://github.com/facebookresearch/sam2), Apache-2.0. Native engine [sam3.cpp](https://github.com/PABannier/sam3.cpp), MIT; setup downloads fixed source archives and builds them externally. This project uses SAM 2.1 Tiny, not SAM 3 text segmentation.
- **ViTMatte:** [Small Composition-1k weights](https://huggingface.co/hustvl/vitmatte-small-composition-1k), Apache-2.0 model metadata. [Matte Anything](https://github.com/hustvl/Matte-Anything), MIT; adapted trimap procedure carries the full MIT notice in `scripts/vitmatte_backend.py` and setup stores it with runtime metadata. [ViTMatte implementation](https://github.com/hustvl/ViTMatte), MIT.
- **Other runtime packages:** Python, PyTorch, transformers, OpenCV, NumPy, Pillow, CMake, Ninja and HyperFrames are installed separately and retain their respective upstream licenses.

Weights, environments, user photos, browser state and credentials are excluded. Future demo media will carry its own source/rights record; it is not covered by the root code license.
