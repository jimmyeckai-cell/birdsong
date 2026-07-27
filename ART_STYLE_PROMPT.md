# Watercolor art prompt (for ChatGPT Pro image generation)

Generate one image per species and save it into `custom_art/` using the exact
filename `art_status.py` lists (species name, spaces → underscores, e.g.
`American_Robin.png`). PNG or JPG both work.

Tip: attach a reference photo of the bird (e.g. from its Wikipedia page) along
with the prompt so the plumage and pose are accurate.

## Prompt template

Replace `{BIRD}` with the common name (and optionally the scientific name):

> A delicate watercolor painting of a **{BIRD}**. Loose, soft watercolor washes
> with visible paper texture and gentle pigment bleeds; no hard outlines, no ink
> lines, no pencil sketch. A single bird in a natural pose, centered. Plain white
> background with the edges of the painting softly feathering into the white —
> no frame, no border, no drop shadow, no vignette box. Vibrant but natural
> plumage colors. No text, no signature, no watermark. Roughly square
> composition.

## Consistency notes

- Keep the **white background + feathered edges** every time — that's what makes
  the mural read as one cohesive wall of paintings.
- One bird per image, centered, similar zoom level across species.
- Avoid busy scenery; a suggestion of a branch/perch is fine, a full landscape
  is not.
- The site downscales whatever you provide to ~560px wide JPEG, so you don't
  need to optimize size — generate at whatever resolution ChatGPT gives you.
