# GYM-NEXUS design system

The redesign is intentionally shared through `base.html` and `app/static/css/style.css`, so existing routes and Jinja data contracts stay unchanged.

## Component library structure

- **App shell**: grouped navigation, collapsible sidebar, responsive mobile rail, workspace breadcrumb, logout, and dark/light theme toggle.
- **Page header**: module title, context line, live workspace status, and one primary action.
- **Panel / Card**: frosted surface, border, depth, responsive spacing, and consistent heading treatment.
- **Stat card**: high-signal KPI label, large value, optional trend/pulse, and staggered entrance motion.
- **AI badge**: consistent cyan signal marker for generated insight, forecast, churn, and recommendation content.
- **Data table**: responsive overflow, compact metadata headers, row hover, status pills, and empty-state copy.
- **Form controls**: shared inputs, selects, textareas, lookup fields, inline validation, and primary/secondary button hierarchy.
- **Detail layout**: panels, status pills, activity lists, and responsive two-column `.panels` grids.
- **Feedback states**: alert styles, skeleton-ready surfaces, empty states, focus-visible rings, and reduced visual noise on mobile.
- **Chat assistant**: persistent AI launcher and conversation surface using the same accent and surface tokens.

## Rollout

1. The app shell and tokens are applied globally to every authenticated module.
2. The dashboard is the flagship surface: KPI cards, AI insight sections, forecasts, retention radar, recommendations, and operational analytics are grouped under the `#insights` command-center anchor.
3. Existing module templates inherit the same panel, form, table, status, responsive, and light-mode behavior without backend changes.

## Interaction contract

- Dark mode is the default; the theme control persists the user choice in `localStorage`.
- The sidebar collapse control persists independently and becomes a horizontal mobile navigation at small widths.
- Existing permissions determine which grouped navigation entries appear.
- Existing form actions, route URLs, and server-rendered data remain unchanged.
