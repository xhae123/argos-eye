<h1 align="center">argos-eye</h1>

<p align="center">
  <em>Pixel-precise visual grounding for Claude Code.</em>
</p>

<p align="center">
  <a href="#"><img alt="PyPI" src="https://img.shields.io/pypi/v/argos-eye.svg"></a>
  <a href="#"><img alt="Python" src="https://img.shields.io/pypi/pyversions/argos-eye.svg"></a>
  <a href="#"><img alt="License" src="https://img.shields.io/pypi/l/argos-eye.svg"></a>
  <a href="#"><img alt="Claude Code" src="https://img.shields.io/badge/claude--code-compatible-5A67D8.svg"></a>
</p>

---

`argos-eye` is a single Claude Code skill that turns an image and a
natural-language target into a verified pixel coordinate. It uses an
iterative zoom-and-refine loop to work around a known limitation of
current vision-language models: they describe well, but they cannot
reliably point.

The project is intentionally narrow. It does one thing — *locate a
described target in an image* — and it leaves screenshot capture,
clicking, and workflow orchestration to the caller.

## Table of Contents

- [Why](#why)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Output Format](#output-format)
- [Scope](#scope)
- [Limitations](#limitations)
- [FAQ](#faq)
- [Development](#development)
- [Citation](#citation)
- [References](#references)
- [License](#license)

## Why

Vision-language models describe images well but struggle to point at
them. On `ScreenSpot-Pro`, GPT-4o scores roughly **0.8%** on one-shot
coordinate prediction; Claude's documentation notes that precise
spatial reasoning is unreliable for small or densely packed targets.

Any agent that needs a pixel-accurate location — to click, crop,
verify, or audit — hits this wall.

Research has consistently shown that multi-step *zoom-and-refine*
pipelines close most of this gap (see [References](#references)).
`argos-eye` is a minimal, production-ready implementation of that
pattern, packaged as a single Claude Code skill so it can be dropped
into any workflow.

## Features

- **Zoom-and-refine loop** — iterative crop-reread until the model
  agrees with itself.
- **Zoom consistency stop** — early termination when two consecutive
  predictions converge.
- **Auditable output** — every intermediate crop and decision is
  persisted next to the result.
- **Coordinate remapping** — results are always reported in the
  original image's pixel space.
- **Graceful failure** — when a target cannot be located the skill
  says so, with the best-effort bounding box and a low confidence
  score, instead of hallucinating.
- **Zero training, zero fine-tuning** — works on top of whatever VLM
  Claude Code is configured with.
- **One skill folder** — no daemon, no server, no plugin manifest.

## Installation

```sh
pip install argos-eye
argos-eye init
```

`argos-eye init` installs the skill at
`~/.claude/skills/argos-eye/` (or the path specified by
`CLAUDE_SKILLS_DIR`) and verifies that Claude Code can see it.

<details>
<summary>Using <code>uv</code></summary>

```sh
uv tool install argos-eye
argos-eye init
```

</details>

<details>
<summary>From source</summary>

```sh
git clone https://github.com/tom-kim/argos-eye
cd argos-eye
pip install -e .
argos-eye init
```

</details>

## Quick Start

In any Claude Code session:

```
/argos-eye image=./screen.png target="Sign in button"
```

`argos-eye` runs the loop, returns a coordinate bundle, and writes a
full audit trail to `./.argos-eye/<timestamp>/`.

## Usage

```
/argos-eye image=<path> target=<description> [options]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `image` | path | *required* | Path to the source image. |
| `target` | string | *required* | Natural-language description of the element to locate. |
| `max_iter` | int | `3` | Maximum zoom-refine iterations. |
| `zoom` | float | `3.0` | Scale factor applied during cropping (3×–5× works best in practice). |
| `stop_on_converge` | bool | `true` | Terminate early when two consecutive predictions agree. |
| `evidence_dir` | path | `./.argos-eye` | Where to persist crops and decisions. |
| `min_confidence` | float | `0.5` | Below this, the call reports "not found" rather than a point. |

## How It Works

```
   ┌──────────── iterate (up to N times) ────────────┐
   │                                                 │
image ──► propose bbox ──► crop ──► re-inspect ──► converged?
                                          │ no            │ yes
                                          └── refine ─────┘ ──► remap ──► output
```

1. **Propose** — the model is asked where the target is in the full
   image and returns a rough bounding box.
2. **Crop** — the region is extracted and optionally zoomed.
3. **Re-inspect** — the model is asked the same question using only
   the crop. It either confirms, tightens, or rejects the bbox.
4. **Converge** — when two consecutive proposals agree within
   tolerance (*zoom consistency*), the loop exits.
5. **Remap** — the final crop-relative bbox is translated back to the
   original image's coordinate system.
6. **Persist** — inputs, crops, intermediate proposals, and the final
   answer are written to `evidence_dir`.

The loop is bounded. If `max_iter` is reached without convergence,
the skill returns its best guess and flags low confidence.

## Configuration

Defaults can be overridden via a `.argos-eye.toml` in the project
root or the user home directory:

```toml
[argos-eye]
max_iter         = 3
zoom             = 3.0
min_confidence   = 0.5
evidence_dir     = ".argos-eye"
```

Skill invocation arguments always take precedence over config file
values, which take precedence over defaults.

## Output Format

Every call returns a single JSON object:

```json
{
  "bbox":        [120, 340, 260, 388],
  "center":      [190, 364],
  "confidence":  0.92,
  "iterations":  2,
  "converged":   true,
  "evidence":    ".argos-eye/2026-04-21T13-57-03Z/"
}
```

If the target cannot be located:

```json
{
  "bbox":        null,
  "center":      null,
  "confidence":  0.18,
  "iterations":  3,
  "converged":   false,
  "evidence":    ".argos-eye/2026-04-21T13-57-03Z/",
  "reason":      "target description did not match any region"
}
```

The `evidence/` folder contains:

```
.argos-eye/<timestamp>/
├── input.png           original image
├── target.txt          target description as submitted
├── iter-0-bbox.json    proposals per iteration
├── iter-0-crop.png
├── iter-1-bbox.json
├── iter-1-crop.png
└── result.json         final output
```

## Scope

| In scope | Out of scope |
|---|---|
| Image + description → coordinate | Taking screenshots |
| Evidence persistence | Clicking / typing / driving a UI |
| Confidence reporting | Orchestrating multi-step workflows |
| Coordinate remapping | Fine-tuning the underlying VLM |

`argos-eye` answers one question: *where in this image is the thing
you described?* Anything before or after that is the caller's
responsibility.

## Limitations

- Targets smaller than roughly **20 pixels** in either dimension are
  unreliable; text-inside-text cases especially.
- Screens above **4K** may require more iterations; accuracy gains
  typically flatten after five.
- Non-English UI labels work but are not systematically evaluated.
- The skill is bounded by the configured VLM's reasoning — it does
  not train, fine-tune, or ensemble models.
- Performance depends on the underlying model's cost and latency;
  three iterations means three image calls.

## FAQ

**Does it capture screenshots?**
No. You provide the image; `argos-eye` locates within it.

**Can it click the button it finds?**
No. It returns coordinates. What you do with them is your choice —
pair it with `pyautogui`, `playwright`, or anything else.

**Does it require internet?**
Only whatever the underlying VLM requires.

**Does it work on non-UI images?**
Yes. The loop makes no assumption that the image is a screenshot. It
has been tested on dashboards, photos, and documents.

**Is the evidence folder safe to delete?**
Yes. It is write-only from the skill's perspective.

## Development

```sh
git clone https://github.com/tom-kim/argos-eye
cd argos-eye
pip install -e ".[dev]"
pytest
```

Contributions are welcome. Before opening a pull request, please:

1. Open an issue describing the change.
2. Keep the scope aligned with the [Scope](#scope) table — feature
   requests that expand beyond *image → coordinate* will be closed.
3. Include a test and, where relevant, an updated example under
   `examples/`.

## Citation

If `argos-eye` is useful in your research or product, a citation or
link back to this repository is appreciated:

```
@software{argos_eye,
  author = {Kim, Tom},
  title  = {argos-eye: Pixel-precise visual grounding for Claude Code},
  year   = {2026},
  url    = {https://github.com/tom-kim/argos-eye}
}
```

## References

The zoom-and-refine pattern is well established in GUI grounding
research. `argos-eye` is a practical implementation, not a novel
technique.

- **R-VLM** — Region-Aware Vision Language Model for Precise GUI
  Grounding. ACL Findings 2025. arXiv:2507.05673.
- **UI-Zoomer** — Uncertainty-Driven Adaptive Zoom-In for GUI
  Grounding. arXiv:2604.14113.
- **Zoom Consistency** — A Free Confidence Signal in Multi-Step
  Visual Grounding Pipelines. arXiv:2604.15376.
- **CropVLM** — Learning to Zoom for Fine-Grained Vision-Language
  Perception. arXiv:2511.19820.
- **OmniParser** — Pure Vision Based GUI Agent. Microsoft, 2024.
  arXiv:2408.00203.
- **GUI-Actor** — Coordinate-Free Visual Grounding for GUI Agents.
  arXiv:2506.03143.

## License

Released under the [MIT License](LICENSE).
