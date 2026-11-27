# Showcase maintenance / 双语展示页维护

`docs/index.html` is the standalone deliverable. It embeds nine canonical assets: the official logo, four plugin icons, the PM-532 schematic and assembly preview, and two Manrope font subsets. No external request is needed to render it. Open it offline or publish the `docs` directory through GitHub Pages. The README uses the 2560 × 1280 PNGs, while the 1280 × 640 SVGs embed their image dependencies and outline their display text.

页面源为 `showcase.template.html` 和 `showcase.i18n.json`；生成文件不要手工修改。中英字典键必须完全一致，URL 的 `lang` 优先于上次保存的偏好。语言、视图和客户端切换按钮支持键盘；复制在浏览器允许时优先使用 Clipboard API，离线环境可回退为选区复制。页面明确区分数字净空验证、无损功率模型与待实测的 PER。

~~~sh
python3 scripts/build_showcase.py
python3 scripts/build_showcase.py --check
python3 tests/showcase_acceptance.py
~~~

Optional artwork regeneration needs `fontTools`, `resvg-py 0.5.0`, a locally licensed CJK font and a sans-serif font for the schematic. Select the appropriate face index for a font collection. Only document outlines are exported; the system CJK font itself is not distributed.

~~~sh
python3 scripts/build_showcase.py --covers \
  --cjk-font /path/to/cjk-font.ttc --cjk-index 11 \
  --schematic-font /path/to/sans-serif.ttf
~~~

The command exports each SVG at **2560 × 1280**, preserving its 2:1 canvas, and records PNG hashes in `assets/cover-manifest.json`. It first renders the unchanged schematic into `assets/schematic-cover.png` at 1640 px width with an explicit font: nested SVG images otherwise lose their text in this rasterizer. The interactive page continues to embed the original vector schematic. PNG scanlines are losslessly recompressed at zlib level 9, with CRC and decoded-data equality checks; all non-image chunks are preserved. System thumbnail generators are unsuitable if they crop to a square. Run the showcase test after regeneration. The manifest binds original asset hashes, release version, CJK face identity and output hashes; the official logo remains byte-for-byte identical to its brand manifest.

Manrope subset provenance is in `assets/font-sources.json`; the original [SIL OFL notice](../plugins/hksop-step3-manufacture/skills/export-packages/references/logo/OFL-Manrope.txt) accompanies the canonical logo resources. This font permission does not grant a license to the rest of the repository.

Before release, check both languages at 1440 × 900 and 390 × 844, all three visual modes, slider keyboard operation, client tabs, command copy, language persistence, document title and URL. Do not call screenshots or static checks a completed functional browser test.
