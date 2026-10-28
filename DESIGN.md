---
version: alpha
name: ForumScope
description: A local forum research workspace with inspectable relevance evidence.
colors:
  primary: "#2f5e3d"
  primary-deep: "#244a30"
  primary-soft: "#dce8d8"
  field-ground: "#f6f1e6"
  surface: "#fffdf8"
  sage: "#7fa37a"
  rule: "#d9cdb5"
  rule-strong: "#b6a98d"
  selection: "#b21e18"
  ink: "#242720"
  graphite: "#4a4a44"
  muted: "#67665f"
  relevance-high: "#2f5e3d"
  relevance-medium: "#88641d"
  relevance-low: "#9b4b22"
  relevance-offtopic: "#656761"
typography:
  display:
    fontFamily: "Georgia, 'Times New Roman', serif"
    fontSize: "clamp(28px, 3vw, 37px)"
    fontWeight: 400
    lineHeight: 1.16
    letterSpacing: "-0.035em"
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.055em"
rounded:
  sm: "4px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "9px 14px"
    height: "42px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "9px 11px"
    height: "43px"
  nav-active:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "8px 10px"
    height: "43px"
  evidence-ruler:
    backgroundColor: "{colors.primary}"
    height: "8px"
---

# Design System: ForumScope

## Overview

**Creative North Star: “The Field Folio of Evidence.”** ForumScope translates the selected botanical folio into a calm, repeatable way to compare public discussion: every answer is registered against the same visible scale, while the content remains unmistakably a working forum-analysis tool. The surface feels considered and precise rather than clinical; the folio informs palette, measured density, italic topic titles, and a single comparison device, never the navigation or controls.

The application uses a deep-green rail against a warm field ground. Results sit on a clean sheet, separated by fine sepia rules. Leaf green carries primary actions and strong-match data; ochre, copper, and graphite distinguish the remaining relevance states. Scarlet is reserved for a selected state, focus, or the ruler's score marker. Standard web forms, tabs, tables, links, and buttons stay familiar and keyboard-operable.

**Key Characteristics:**
- Field-ground warmth with a dark leaf-green navigation anchor.
- Georgia display titles paired with a readable system UI sans.
- Flat surfaces; hairline rules and tonal fields establish hierarchy.
- Every ranked reply shares one exact 0–100 evidence baseline.
- Scarlet is a precision signal, not a second primary-action color.

## Colors

The palette is drawn from warm folio stock, leaf and sage inks, graphite text, and a restrained scarlet register mark. The token values below match the implementation's CSS custom properties.

### Primary
- **Leaf-field green** (`#2f5e3d`): navigation rail, primary buttons, high-relevance state, and the filled portion of evidence rulers.
- **Canopy green** (`#244a30`): active navigation and the primary button's hover state.
- **Pressed-sage tint** (`#dce8d8`): quiet selected surfaces and secondary control hover states.
- **Sage ink** (`#7fa37a`): scrollbar thumb and supportive measurement accents.

### Neutral
- **Warm plate ground** (`#f6f1e6`): the application canvas and the shared field behind the work.
- **Specimen sheet** (`#fffdf8`): input and collection surfaces.
- **Sepia rule** (`#d9cdb5`): standard separators and low-emphasis borders.
- **Strong sepia rule** (`#b6a98d`): input outlines and structural dividers.
- **Primary ink** (`#242720`): headings and primary text.
- **Reading graphite** (`#4a4a44`): body copy, excerpts, and supporting explanations.
- **Metadata graphite** (`#67665f`): captions and secondary labels.

### Data states
- **Registered scarlet** (`#b21e18`): active tab underline, focus ring, and the exact-score marker on each ruler.
- **High match** (`#2f5e3d`): a strong relationship to the topic.
- **Moderate match** (`#88641d`): partial evidence.
- **Low match** (`#9b4b22`): weak topical correspondence.
- **Outside focus** (`#656761`): the neutral off-topic state.

### Named Rules
**The Registered Evidence Rule.** Scarlet marks a specific selected or measured point; it never floods a whole panel.

## Typography

**Display Font:** Georgia, with Times New Roman and serif fallbacks.
**Body Font:** system UI sans-serif stack (`ui-sans-serif`, system-ui, Segoe UI).
**Label Font:** the body stack, in compact tracked uppercase for metadata.

**Character:** the serif carries the folio's restrained editorial voice in page and topic titles. The sans remains neutral and highly legible for forms, responses, scores, and navigation. Numerals use tabular figures wherever comparison matters.

### Hierarchy
- **Display** (400, `clamp(28px, 3vw, 37px)`, 1.16): page title, with tight `-0.035em` tracking.
- **Topic title** (Georgia italic, 20px, 1.32): parsed discussion and preview headings.
- **Section title** (650–680, 14–17px): work areas and result summaries.
- **Body** (400, 15px, 1.5): the default interface measure; long descriptions cap at 70ch.
- **Excerpt** (400, 13px, 1.62): full forum answer text in ranked rows.
- **Label** (650–720, 9–12px): state names, metadata, and evidence values; compact without replacing body copy.

### Named Rules
**The Two Voices Rule.** Serif is reserved for titles; operational copy, controls, evidence, and status stay in the system sans.

## Layout

The desktop shell uses a 232px left rail and a flexible workspace. The main collection column shares the first view with a 252px method rail, separated by a 27px gap; above 1600px the method rail widens to 278px. The top bar is 62px high. Content starts at 32px from the top and uses 35px horizontal padding, growing to 48px on wide screens.

The composition is task-first: source tabs and collection controls precede the discussion preview, then ranked responses and the supporting score legend. Repeated responses remain in a single list rather than nested cards. A 4px half-step supports tight control groups; the recurring spacing rhythm uses 8px, 16px, 24px, and 32px values, with 27px/35px shell gaps where the measured layout requires them.

At 1160px the rail and side column contract. At 930px the method rail moves below the work column. At 720px the sidebar becomes a top brand bar with horizontal navigation, source controls stack, and the score ruler remains full-width with explicit ticks. At 440px padding and headings tighten while content keeps a 320px minimum viewport. Reduced-motion preferences remove authored transitions and reveals.

### Named Rules
**The Shared Scale Rule.** Ranked answers always use one fixed 0–100 ruler with the same tick positions; the comparison remains valid at every breakpoint.

## Elevation & Depth

The system is predominantly flat. Warm ground, paper-white surfaces, forest fields, and fine borders provide the hierarchy. A small offset shadow supports the primary action only on hover (`0 3px 8px rgb(36 74 48 / 16%)`); the larger soft shadow belongs to transient toast feedback (`0 7px 18px rgb(40 47 36 / 12%), 0 2px 4px rgb(40 47 36 / 9%)`). Controls do not float above the work area at rest.

### Named Rules
**The Flat Folio Rule.** Use tonal surfaces and hairline rules first; reserve shadows for primary-action hover and feedback that must temporarily sit above the page.

## Shapes

Operational rectangles use a restrained 4px radius. Rank markers and status dots are circular because they encode a point or state, not because every container needs a pill shape. Borders remain 1px and sepia-toned; selected states use a 2px underline rather than a thick side stripe.

## Components

### Buttons
- **Primary:** leaf-green fill, warm-white text, 42px minimum height, 9px × 14px padding, 4px corners.
- **Hover:** canopy-green fill and a low offset shadow; disabled controls use a neutral surface and remain visibly inactive.
- **Quiet:** transparent surface with strong sepia border and green text; hover adds a pale green field.
- **Focus:** a 3px scarlet outline with 3px offset.

### Inputs / Fields
- **Text input:** 43px height, warm-white fill, 1px strong-sepia outline, 4px corners, 9px × 11px padding.
- **Textarea:** same field vocabulary, 10px × 11px padding, user-resizable vertically.
- **Focus:** forest border and a subtle 3px tonal ring. Placeholder copy stays graphite, not a low-contrast gray.
- **File field:** dashed sepia boundary; the actual native file input remains keyboard-focusable and labeled.

### Navigation
- **Desktop:** fixed-width leaf-green rail; active item uses a deeper green field and a narrow scarlet registration mark.
- **Mobile:** same items become a horizontally scrollable top navigation; no desktop rail is squeezed into a narrow screen.

### Tabs
- **Source tabs:** native buttons with tab semantics, arrow-key navigation, and one selected state; the active tab receives a 2px scarlet underline.

### Relevance labels
- **High / medium / low / off-topic:** compact text labels paired with distinct color roles. The label is always written; color is not the sole state cue.

### Evidence ruler
- **Signature component:** each ranked item receives an equal-width 8px track, 0/25/50/75/100 tick labels, a forest score fill, and one narrow scarlet marker. The same scale and geometry repeat for every response.

### Toast feedback
- **Depth:** one soft offset shadow, persistent readable copy, and semantic status/alert roles; the toast is transient and does not replace inline field errors.

## Do's and Don'ts

### Do:
- **Do** keep the navigation and primary task anchored by leaf green.
- **Do** use the registered 0–100 ruler to compare replies on a common baseline.
- **Do** pair every relevance color with a written label and a numeric score.
- **Do** let results, filters, and explanations remain plain text and native controls.
- **Do** keep demo content visibly marked synthetic and keep LLM use opt-in.

### Don't:
- **Don't** use botanical drawings or textures as decoration; the folio world lives in palette, type, density, and measurement.
- **Don't** use scarlet as a second primary-action color or as a large decorative field.
- **Don't** use decorative gradients, glass, or floating-card grids to imply importance.
- **Don't** let hash similarity be presented as a moderation verdict; it is a deterministic heuristic, not a decision about people.
