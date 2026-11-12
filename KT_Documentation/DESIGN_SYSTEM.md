# Design System

## 1. Design Direction

- **Style:** High-Density SRE Command Center / Technical Observability Dashboard
- **Mood:** Authoritative, high-clarity, forensic, mission-critical, responsive
- **Design Principles:**
  1. **Clarity Over Clutter:** Present operational telemetry, metrics, and error rates with immediate visual hierarchy.
  2. **Forensic Traceability:** Every metric must directly link or drill down to verifiable ground-truth log lines and line numbers.
  3. **Zero-Latency Visual Feedback:** Micro-interactions (stopwatches, loading spinners, telemetry pills) indicate pipeline progress in real time.
  4. **Dynamic Adaptability:** Layout and UI labels automatically adjust to dynamic service counts and branding loaded via `.env` and `/api/config`.

---

## 2. Brand Identity

- **Brand Name:** ServiceLog Intelligence Hub (dynamically rendered from `APP_NAME` in `.env`)
- **Organization:** LogTrax Enterprise (dynamically rendered from `APP_ORG_NAME` in `.env`)
- **Logo Rules:**
  - Placed in top-left navigation bar (`frontend/img/LogoBlue.png` or `BillTraxR_logo.png`).
  - Maximum height: `40px`; aspect ratio strictly preserved.
  - Accompanied by dynamic navigation pill badge (`APP_NAV_BADGE`: *"Observability Hub"*).
- **Brand Voice:** Objective, analytical, deterministic, precise, and forensic.

---

## 3. Color Palette

The platform uses an executive palette engineered for long-session monitoring and high contrast:

| Token Name | Hex Code | Purpose / Application |
| :--- | :--- | :--- |
| **Primary Accent** | `#FF9C1D` | Interactive focus rings, active service pills, CTA hover highlights |
| **Hover Primary** | `#F58700` | Pressed buttons, active hover states |
| **Deep Executive Navy** | `#091E3E` | Navigation headers, stat card headers, dark structural accents |
| **Royal Tech Blue** | `#00468E` | Data throughput badges, active filters, informational badges |
| **Diagram Slate** | `#597A9D` | Subtitles, helper text, inactive borders, secondary labels |
| **Canvas Background** | `#F8FAFC` | Main dashboard page background |
| **Surface White** | `#FFFFFF` | Card bodies, modal containers, data tables |
| **Surface Subtle** | `#F1F5F9` | Table row hover, input backgrounds, disabled states |
| **Text Primary** | `#0F172A` | Core headings, primary metric numbers, log table text |
| **Text Secondary** | `#475569` | Body descriptions, card labels, secondary attributes |
| **Text Muted** | `#64748B` | Timestamps, micro-copy, pagination status |
| **Border Default** | `#E2E8F0` | Structural card borders, divider lines, table borders |
| **Success Emerald** | `#10B981` | SLA compliance, 200 OK statuses, healthy service pills |
| **Warning Amber** | `#F59E0B` | Warning-level logs, degraded performance, latency spikes |
| **Error Crimson** | `#DC2626` | Critical service breaks, fatal logs, error causes, format exceptions |

---

## 4. Typography

100% offline robust font stack utilizing modern system font fallbacks with zero external CDN font requests:

- **Heading Font:** `'Rubik', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif`
- **Body Font:** `'Montserrat', 'Rubik', system-ui, -apple-system, 'Segoe UI', sans-serif`
- **Monospace / Code Font:** `'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace`
- **Type Scale:**
  - **H1 (Dashboard Title):** `28px` / `700 bold` / Line Height: `1.2`
  - **H2 (Section Headings):** `20px` / `600 semi-bold` / Line Height: `1.3`
  - **H3 (Card Titles / Subheaders):** `16px` / `600 semi-bold` / Line Height: `1.4`
  - **Body (Standard Copy):** `14px` / `400 regular` / Line Height: `1.5`
  - **Small (Badges, Metadata, Timestamps):** `12px` / `500 medium` / Line Height: `1.4`
  - **Code / Forensic Lines:** `12px` / `400 regular` / Line Height: `1.6`

---

## 5. Spacing Scale

Based on an 8-point harmonic grid:
- **Base Unit:** `4px`
- **Scale:**
  - `4px` (xs): Tight badge padding, pill margins
  - `8px` (sm): Input field inner padding, button icon gaps
  - `12px` (md): Card interior padding, filter pill spacing
  - `16px` (lg): Grid column gutters, standard component margins
  - `24px` (xl): Section dividers, metric card internal padding
  - `32px` (2xl): Page layout margins, modal spacing
  - `48px` (3xl): Major layout breaks

---

## 6. Border Radius

- **Small (`rounded-sm`):** `4px` (Inline code blocks, small badges)
- **Medium (`rounded-md`):** `8px` (Form inputs, secondary buttons)
- **Large (`rounded-xl`):** `12px` (Dashboard metric cards, modal dialogs)
- **Pill (`rounded-full`):** `9999px` (Status badges, telemetry tags, service filter buttons)

---

## 7. Elevation & Shadows

- **Subtle (`shadow-sm`):** `0 1px 2px 0 rgba(0, 0, 0, 0.05)` (Default card elevation)
- **Interactive (`shadow-md`):** `0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)` (Hover state on cards & buttons)
- **Float / Modal (`shadow-xl`):** `0 20px 25px -5px rgba(0, 0, 0, 0.15), 0 10px 10px -5px rgba(0, 0, 0, 0.04)` (Response panels, dropdown menus)
- **Orange Glow:** `0 0 15px rgba(255, 156, 29, 0.35)` (Active query input focus ring)

---

## 8. Button Components

### Primary Button (Action / Execute Query)
- **Background:** Gradient from `#FF9C1D` to `#F58700`
- **Text:** `#FFFFFF`, `font-weight: 600`
- **Padding:** `10px 20px`
- **Hover:** Elevated shadow, slight brightness increase
- **Active:** Scale `0.98`

### Secondary Button (Filter / Reset / Reindex)
- **Background:** `#FFFFFF` with border `1px solid #E2E8F0`
- **Text:** `#475569`, hover to `#0F172A`
- **Hover:** Background `#F8FAFC`

### Danger Button (Clear / Purge)
- **Background:** `#DC2626`
- **Text:** `#FFFFFF`
- **Hover:** Background `#B91C1C`

### Loading State
- Shows embedded SVG animated spinner (`animate-spin`), opacity `0.75`, `pointer-events: none`, cursor `not-allowed`.

---

## 9. Form Inputs

### Text & Search Inputs
- **Default:** Background `#FFFFFF`, border `1px solid #CBD5E1`, text `#0F172A`, placeholder `#94A3B8`.
- **Focus:** Border color `#FF9C1D`, box shadow `0 0 0 3px rgba(255, 156, 29, 0.25)`.
- **Error:** Border color `#DC2626`, box shadow `0 0 0 3px rgba(220, 38, 38, 0.2)`.

---

## 10. Cards & Containers

- **Metric Cards:** White background (`#FFFFFF`), `1px solid #E2E8F0` border, `12px` border radius, subtle header background `#091E3E` with light title text.
- **Log Table Container:** Elevated white card, sticky header row with subtle slate background (`#F8FAFC`), monospace log rows with alternating hover highlights.

---

## 11. Navigation Bar

- **Layout:** Sticky top header (`h-16`), background `#091E3E` with subtle bottom border.
- **Left:** Organization logo, application title, dynamic subtitle badge.
- **Center:** Quick-jump navigation links (*Overview*, *Services*, *Error Triage*, *AI Query*, *Log Explorer*).
- **Right:** SLA compliance pill (`SLA: 95.0%`), Reindex button, backend status pulse indicator.

---

## 12. Component States

- **Loading:** Skeleton loader bars or pulsating SVG spinners. Stopwatch timer active in milliseconds.
- **Empty:** Clear SVG illustration, informative message (e.g., *"No log errors match the active filter criteria"*), reset button.
- **Error:** Crimson alert banner (`#FEF2F2` background, `#DC2626` border) with actionable error description and request ID.
- **Success:** Emerald badge (`#ECFDF5` background, `#10B981` text) with check icon.

---

## 13. Icons

- **Library:** Lucide Icons (`lucide.min.js`, offline bundled).
- **Default Size:** `16px` for inline badges/table actions; `20px` for navigation and card headers; `24px` for hero buttons.
- **Style:** Clean outline with `stroke-width: 2`.

---

## 14. Responsive Breakpoints

- **Mobile (`< 640px`):** Stack metric cards into single column; wrap filter pills into scrolling horizontal bar.
- **Tablet (`640px - 1024px`):** Two-column metric card grid; condensed tabular log view.
- **Desktop (`> 1024px`):** Full four-column KPI grid; split-pane AI response view with simultaneous forensic code inspector.

---

## 15. Accessibility (a11y) Guidelines

- **Semantic HTML:** Strict usage of `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<table>`.
- **High Contrast:** All body text meets WCAG AA standards (minimum `4.5:1` contrast ratio against backgrounds).
- **Keyboard Navigation:** Full tab order navigation across search inputs, service filter pills, and query submit buttons.
- **Focus Indicators:** Visible 2px focus outlines (`#FF9C1D`) on all interactive controls.
- **Color Independence:** Error and success states always pair color with text labels and distinct icons (check marks, alert triangles).

