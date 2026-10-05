# Travel story revision

The previous 4.8-second uniform montage is preserved in the parent folder. This 6-second revision uses an explicit editing script: departure → city wandering → mountains → lake. These are stock photos from different locations, so this is a conceptual montage, not a documented real itinerary.

- Subject heights: 29%, 23%, 51%, 22%, 41%, 25%, 66%, 7%.
- The market and final lake shot hold for two beats; other shots hold for one, at 100 BPM.
- Small subjects receive modest 1.25–1.35 framing zooms and positioning where suitable. The last boat stays intentionally small as a wide closing shot.
- Two landscape originals are downloaded at 3200px and segmented again, avoiding the baseline portrait-cover pixel enlargement. No source detail is reconstructed; motion blur and occlusion remain.
- Requested anchors for market/cyclist are limited to keep the photo covering the frame. See the actual framing in edit-review.json.

![Story revision](preview.gif)

[Editing script](EDIT-SCRIPT.md) · [Framing and quality measurements](edit-review.json) · [Shot board](storyboard.jpg) · [MP4 and Skill ZIP](https://github.com/HenryZABA/collage-film/releases/tag/v0.4.0)

## Reproduce

Set up the models, then download this revision's credited photos to a fresh directory:

```bash
python3 examples/travel/story/download.py --output ./travel-story-photos
python3 scripts/make.py \
  --images travel-story-photos/lake-boat.jpg travel-story-photos/van.jpg travel-story-photos/kimono.jpg travel-story-photos/hikers.jpg travel-story-photos/coastal-camper.jpg travel-story-photos/hanoi.jpg travel-story-photos/street-market.jpg travel-story-photos/cyclist.jpg \
  --subjects examples/travel/story/subjects.json \
  --edit-script examples/travel/story/edit-script.json \
  --output ./my-travel-story --platform instagram --ratio 9:16 \
  --demo-music --grade warm-film --check
```

The input order is unchanged; the script controls final order, BPM, durations, zoom and subject anchor. Source hashes bind decisions to the viewed normalized PNGs. If your image decoder/PNG encoder produces different bytes, verify the actual image before updating the binding. Check cutouts, subject detail and transition alignment before rendering. Photos remain governed by the [Unsplash License](https://unsplash.com/license), with exact author/page/download URL/hash in sources.json. The root code license does not cover stock imagery.
