# VinFast AI Sales Advisor — Design System

## 1. Design direction

The interface should feel like a modern VinFast digital showroom:

- simple
- modern
- premium
- product-first
- spacious
- confident
- easy to understand

The customer should focus on the vehicle and the current decision, not on menus or dashboard chrome.

Do not clone the official VinFast website pixel-for-pixel. Adapt the visual language to an AI-assisted consultation product.

## 2. Core principles

1. The vehicle is the hero.
2. One main decision per screen.
3. Use whitespace before decoration.
4. Use restrained blue only for primary actions and selected states.
5. Prefer borders and spacing over heavy shadows.
6. Keep typography concise and medium-weight.
7. Customer pages must not use permanent sidebars.
8. Advisor and Admin pages may use practical operational navigation.
9. 3D is progressive enhancement and must have a poster fallback.
10. Never present a generic car as a VinFast model.

## 3. Color tokens

Use existing project tokens when available. Otherwise start with:

```css
--background: #ffffff;
--surface: #f5f7fa;
--surface-strong: #eef2f7;
--foreground: #101828;
--muted-foreground: #667085;
--border: #e4e7ec;

--primary: #1464f4;
--primary-hover: #0f52cc;
--primary-foreground: #ffffff;

--success: #12805c;
--warning: #b76e00;
--danger: #c83232;

--dark-surface: #0d1117;
--dark-foreground: #ffffff;
```

Rules:
- white and light neutral surfaces dominate;
- blue is used for primary CTA, focus, and selected states;
- red is reserved for errors;
- green is reserved for success;
- avoid multi-color decorative gradients.

## 4. Typography

Preferred:
- existing project font;
- Geist;
- Inter;
- system sans-serif.

Do not bundle proprietary automotive fonts.

Suggested hierarchy:

| Role | Desktop | Mobile | Weight |
|---|---:|---:|---:|
| Hero title | 48–64px | 36–44px | 500–600 |
| Page title | 36–44px | 28–34px | 500–600 |
| Section title | 24–30px | 22–26px | 500–600 |
| Card title | 18–22px | 18–20px | 500–600 |
| Body | 16–18px | 15–17px | 400 |
| Label | 13–15px | 13–15px | 500 |
| Caption | 12–14px | 12–14px | 400 |

Use short headings. Avoid large blocks of bold text.

## 5. Spacing and layout

Base spacing:
- 4px
- 8px
- 12px
- 16px
- 24px
- 32px
- 48px
- 64px
- 96px

Containers:
- customer reading width: 720–880px;
- showroom content may use the full viewport;
- advisor/admin content width: 1200–1440px.

Customer layout:
- compact top header;
- main content centered;
- no permanent sidebar;
- horizontal progress;
- contextual drawers and bottom sheets;
- vehicle controls in a bottom tray.

## 6. Components

### Buttons

Primary:
- blue background;
- white text;
- 44px minimum height;
- 6–8px radius;
- restrained hover darkening.

Secondary:
- white or transparent background;
- dark text;
- subtle border.

Ghost:
- no permanent surface;
- used for low-priority actions.

### Cards

- use cards only when grouping is necessary;
- 8–12px radius;
- subtle border;
- little or no shadow;
- do not place every section inside a card.

### Chips

Use for:
- quick replies;
- time slots;
- selected preferences;
- compact customer-profile summary.

Chips may use pill shapes, but standard buttons should remain more restrained.

### Navigation

Customer:
- horizontal header;
- compact;
- logo/wordmark left;
- primary CTA right;
- mobile drawer only when opened.

Advisor/Admin:
- sidebar allowed;
- simple labels;
- clear active state.

## 7. Vehicle showroom

The vehicle occupies the largest visual area.

When 3D is available:
- drag to rotate;
- limited zoom;
- reset view;
- static poster before loading;
- loading and error state;
- reduced-motion support.

Vehicle controls:
- bottom tray;
- collapsible;
- only one group expanded at a time.

Control groups:
- paint color;
- wheel;
- exterior/interior;
- highlights;
- reset.

Do not show all controls simultaneously in a permanent column.

## 8. Motion

- 200–350ms transitions;
- subtle opacity and transform;
- no decorative looping animations;
- respect `prefers-reduced-motion`;
- never block the main CTA while 3D is loading.

## 9. Responsive behavior

At 360px:
- single-column layout;
- compact header;
- bottom-sheet vehicle controls;
- consultation summary collapses;
- recommendation cards stack;
- advisor/admin sidebar becomes a drawer.

At 768px:
- wider conversation area;
- comparison may scroll horizontally.

At 1024px and above:
- vehicle showroom may use full viewport;
- advisor review may use two columns;
- customer consultation remains centered rather than becoming a dashboard.

## 10. Do and do not

Do:
- emphasize vehicle imagery;
- use generous whitespace;
- keep UI copy concise;
- prioritize clear next actions;
- make the whole demo feel coherent.

Do not:
- clone the official website exactly;
- use unauthorized logos, fonts, photos, or 3D assets;
- use permanent sidebars on customer pages;
- use excessive gradients or glowing effects;
- use generic-car assets labelled as VinFast;
- make the chatbot look like a technical support dashboard.
