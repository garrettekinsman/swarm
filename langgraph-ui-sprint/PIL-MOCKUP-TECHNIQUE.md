---
*Prepared by **Agent: Mei (梅)** — PhD candidate, Tsinghua KEG Lab. Specialist in inference optimization, open-source AI ecosystems.*
*Running: anthropic/claude-sonnet-4-6*

*Human in the Loop: Garrett Kinsman*

---

# PIL Mockup Technique

**Context:** Visualizing generated web pages on the Mac Mini without a headless browser.  
**Output example:** `~/.openclaw/media/eldr-swarm-mockup.png`

---

## Why We Need It

The Mac Mini (M-series, agent sandbox) doesn't have:
- Chrome / Chromium (no GUI apps in sandbox)
- Playwright — needs browser binaries, blocked by sandbox or not installed
- wkhtmltoimage — WebKit-based renderer, requires X11 or macOS display
- `cutycapt`, `webkit2png`, or similar — same issue

The standard "just open the browser and screenshot" pipeline doesn't work here. PIL is pure Python, always available, no system dependencies.

**Use case:** Visual QA after a swarm run, to confirm the page structure/colors look sane before human review. Not for pixel-perfect rendering. For "does the layout make sense and do the colors match the spec."

---

## How It Works

PIL (`Pillow`) is used to draw a schematic representation of the HTML page structure:

1. **Parse the design spec** (or the generated HTML/CSS) for key values:
   - Background color, accent colors, font families
   - Section names and rough proportions (nav ~60px, hero ~400px, etc.)

2. **Create a canvas** — typically 1280×900px (desktop viewport approximation):
   ```python
   from PIL import Image, ImageDraw, ImageFont
   
   img = Image.new("RGB", (1280, 900), color="#0D1117")
   draw = ImageDraw.Draw(img)
   ```

3. **Draw sections as colored rectangles** with labels:
   ```python
   # Nav bar
   draw.rectangle([(0, 0), (1280, 60)], fill="#161B22")
   draw.text((40, 20), "EldrChat — nav", fill="#F0F6FC", font=font_sm)
   
   # Hero
   draw.rectangle([(0, 60), (1280, 460)], fill="#0D1117")
   draw.text((640, 200), "Privacy-First Messaging", fill="#FFFFFF", font=font_lg, anchor="mm")
   draw.text((640, 260), "Tagline text here", fill="#8B949E", font=font_sm, anchor="mm")
   
   # CTA button (approximate)
   draw.rectangle([(540, 300), (740, 340)], fill="#7C3AED")
   draw.text((640, 320), "Download Free", fill="#FFFFFF", font=font_sm, anchor="mm")
   
   # Features section
   draw.rectangle([(0, 460), (1280, 700)], fill="#161B22")
   # 3-column grid approximation
   for i, (title, desc) in enumerate(features):
       x = 160 + i * 320
       draw.rectangle([(x, 490), (x+280, 690)], fill="#21262D", outline="#30363D")
       draw.text((x+140, 540), title, fill="#F0F6FC", font=font_sm, anchor="mm")
   ```

4. **Save:**
   ```python
   img.save("/Users/garrett/.openclaw/media/eldr-swarm-mockup.png")
   ```

---

## Color Source

Pull colors directly from the design spec or CSS custom properties. For the EldrChat swarm:

| CSS Variable / Usage | Hex |
|---------------------|-----|
| `--color-bg` / body background | `#0D1117` |
| `--color-surface` / cards, nav | `#161B22` |
| `--color-border` | `#30363D` |
| `--color-text-primary` | `#F0F6FC` |
| `--color-text-muted` | `#8B949E` |
| `--color-accent` | `#7C3AED` (violet) |
| `--color-accent-hover` | `#6D28D9` |

If parsing from CSS: use regex on `:root` block or `--var` declarations.

---

## When to Use This vs Alternatives

| Method | When to Use | Requirement |
|--------|-------------|-------------|
| PIL mockup | Always available, quick layout check | Python + Pillow |
| `playwright screenshot` | When you need real rendered output | `playwright install chromium` (not in sandbox) |
| `wkhtmltoimage` | Full HTML rendering on CI/Linux | wkhtmltopdf installed, display available |
| `webkit2png` | macOS-native, works without display | macOS, Python 2 originally (unmaintained) |
| Manual browser open | When you're at a GUI machine | You, a mouse, and a browser |

**For pipeline-generated pages in this workspace:** PIL is the pragmatic default. Saves time, no setup, produces something better than nothing.

---

## Limitations

1. **Not real rendering.** Fonts don't load from Google Fonts. CSS layout (flexbox, grid) isn't computed. What you see is an approximation based on hardcoded section proportions.
2. **No JS.** Any dynamic content (mobile menu, animations, scroll behavior) is invisible.
3. **Typography is fake.** Default PIL fonts are bitmap. You can load a TTF (`ImageFont.truetype()`), but you still won't match the actual web font rendering.
4. **Section heights are hardcoded.** Need to update manually if the page structure changes.
5. **No responsive behavior.** One fixed viewport only.

---

## How to Improve

**Short term (no system changes):**
- Load a real TTF font: `ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)`
- Parse actual CSS for color values instead of hardcoding
- Pull section proportions from HTML heading structure

**With playwright installed:**
```bash
pip install playwright && playwright install chromium
```
Then:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"file://{html_path}")
    page.screenshot(path=output_png)
    browser.close()
```
This gives actual rendered output. PIL mockup can be retired once playwright is available.

**With wkhtmltoimage (on Linux nodes like Framework1):**
```bash
ssh framework1 "wkhtmltoimage --width 1280 input.html output.png"
# Then scp the png back
```
Viable if you need real rendering urgently and playwright isn't local.

---

## Pattern in Practice

The swarm run on 2026-03-24 followed this flow:
1. `web_swarm.py` ran and produced `web-test/index.html` (18:09)
2. PIL mockup generated separately post-run (18:15) → `eldr-swarm-mockup.png`
3. Mockup sent to Discord for visual review

The PIL script is **not** embedded in `web_swarm.py` — it's run manually or as a post-step. Consider adding a `--mockup` flag to `web_swarm.py` that runs PIL rendering automatically after successful file output.
