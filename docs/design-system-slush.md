# Design system: "Slush" (owner's choice, 2026-09-28)

Source: the owner pasted a style reference extracted from slush.app
("inflatable sticker universe on pastel paper"). This file is the working
copy for the crawler's dashboard; the adaptation rules at the end bind.

## Tokens

Colors:
- Carbon #000000: text, 1px outlines on every interactive element, filled CTA.
- Paper White #ffffff: canvas, cards, outlined button fills, text on dark fills.
- Sky Wash #dceeff: hero / primary section ground.
- Concrete Gray #cccccc: secondary section ground.
- Soft Mist #e9e9e9: subtle tints, disabled states.
- Electric Blue #4da2ff: brand surface and decoration only (never a button or link colour).
- Sticker palette, used together as a set, never one "accent": Mint Pop #55db9c,
  Lavender #e9ccff, Ember #fb4903, Sunburst #ffd731, Voltage Violet #5c4ade.

Type:
- Display: Lateral 800 (commercial; substitute an OFL face such as Bowlby One or
  Antonio), line-height 0.75-0.80, only for display words.
- UI: Aeonik Pro 500/700 (commercial; substitute Inter, OFL). Body 12-16px weight
  500, letter-spacing -0.01em; nav, buttons and uppercase labels weight 700 with
  0.030-0.032em; subheads 24-30px 700; large support heading 64px.
- Scale: 12, 13, 14, 15, 16, 24, 30, 64 (UI); 70, 110, 160, 200 (display).

Shape and space:
- 4px base; spacing 4 8 12 16 20 24 28 32 40 44 48 60 80 128.
- Radius: pills and buttons fully round; cards 20px; elevated cards 40px; body 30px;
  never under 16px for cards.
- Every interactive element and card: 1px solid #000000 outline.
- No box-shadows, no gradients anywhere. Elevation = colour bands and outlines.
- Page max width 1440px; section gap 48px; card padding 24px.

Components (from the reference):
- Pill nav button: white fill, 1px black outline, 700 12-14px, 0.032em.
- Filled CTA: black fill, white text, pill; one per screen.
- Outlined ghost button: white fill, black outline and text, pill.
- Logo mark: round black-outlined badge.
- Marquee banner: full-bleed black band, white uppercase 12-13px text scrolling.
- Stickers: flat shapes in the sticker colours with 1px black outline, slightly
  rotated, placed loosely around display type.
- Section bands alternate #dceeff, #ffffff, #cccccc.

Motion (reference): only the marquee scrolls, plus small hover transitions.

## Adaptation rules for a working dashboard (bind)

- It is a tool, not a landing page: display type (the substitute face) only for the
  wordmark and one hero word per page, at sizes that fit the window (70-110px), never
  for tables, numbers or labels.
- Text contrast: body and labels are black on white, Sky Wash, Lavender or Soft Mist
  (all well above 4.5:1). Never put text on Electric Blue, Mint Pop or Sunburst
  unless it is black and at least 4.5:1; never white text on those.
- Meaning: status colours come from the sticker set, always with a word and an
  outline, never colour alone: running = Electric Blue sticker + "Running",
  finished = Mint Pop sticker + "Finished", stopped = Soft Mist + "Stopped",
  failed = Ember sticker + "Failed". (The reference says Mint Pop is not a success
  colour; here it is a sticker next to the word, which keeps the look.)
- Motion: the thinking-orbs dotted orbs are the one living element (the owner's
  request), on every long job: starting a crawl, a running crawl, loading results,
  exporting, checking and installing an update. Under reduced motion, words only.
  The marquee may carry live crawl status. Nothing else moves.
- Fonts are bundled as files (the Windows app is offline): Inter 400/500/700 and
  the display face, OFL licence texts shipped next to them.
- Keyboard and screen reader: visible focus ring (2px black outline, offset 2px) on
  every control; the orb canvas hidden from screen readers with the words in a
  status region.
