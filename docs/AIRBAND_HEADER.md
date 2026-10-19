# N0JCG Air Band Scanner Header

This document records the header design and behavior used by the N0JCG Air Band Scanner. It is intended as a reusable reference for future N0JCG receiver applications.

## Purpose

The header provides the persistent product identity and the small set of application-wide controls that operators need before opening the operator menu:

- N0JCG brand mark and product name
- Trial status and countdown control
- Operator menu button
- Connection status indicator

The main receiver controls remain below the header in the dark-blue scan panel.

## Structure

The implementation is in `web/index.html`:

```html
<header>
  <div class="brand-lockup">
    <img class="brand-logo"
         src="/assets/N0JCG_Header_Dark_Approved.png"
         alt="N0JCG Open Radio Platform">
    <span class="brand-divider" aria-hidden="true"></span>
    <h1>Air Band Scanner</h1>
  </div>

  <div class="header-actions">
    <button id="trialStatus" class="trial-badge" type="button" disabled>
      Trial 05:00
    </button>
    <button id="menuToggle" class="menu-button" type="button"
            aria-expanded="false"
            aria-controls="operatorMenu"
            aria-label="Open operator menu">
      ☰ <span>Menu</span>
    </button>
    <span id="status" class="pill warn">CONNECTING</span>
  </div>
</header>
```

## Visual standard

The header uses the N0JCG dark navy background (`#0a1f44`) with white text. The approved dark-header logo is used without modification. The product title is separated from the logo by a subtle white divider.

The relevant styling is in `web/brand.css`:

- Desktop minimum height: `72px`
- Desktop horizontal padding: `16px max(24px, calc((100vw - 1200px) / 2))`
- Logo width: `150px`, maximum height `34px`
- Brand lockup: horizontal flex layout, vertically centered
- Product title: compact white text with no wrapping on wide screens
- Mobile minimum height: `64px`
- Mobile logo width: `132px`, maximum height `30px`

`web/app.css` supplies the application-level action styling, including the trial badge, menu button, and status pill.

## Header controls

### Trial status

`#trialStatus` is managed by `web/app.js` and the registration state returned by `/api/status`:

- Unregistered trial: displays the remaining time, such as `Trial 04:32`.
- Expired trial: changes to `Restart Trial` and becomes actionable.
- Registered installation: the control is hidden.
- While the five-minute trial is counting down, the control is disabled.

The same control is used for the expired-trial restart action; there is no separate restart button.

### Operator menu

`#menuToggle` opens the slide-in `#operatorMenu`, which contains registration, receiver tuning, receiver location, airport-code lookup, and FFT candidate tools. The button must retain:

- `aria-expanded="false|true"` state synchronization
- `aria-controls="operatorMenu"`
- An accessible label of `Open operator menu`

The menu can be closed with its Close button, the backdrop, or the Escape key.

### Connection status

`#status` reports the browser-to-application connection state:

- `CONNECTING` during initial load
- `READY` when `/api/status` responds successfully
- `OFFLINE` when the status request fails

The `warn`, `ok`, and `pill` classes provide the visual state colors.

## Responsive behavior

At widths below `720px`, the header changes to a stacked layout. The brand lockup remains readable, the logo shrinks, and the product title may wrap. Header controls remain available without requiring horizontal scrolling.

Any future header additions should preserve:

- A usable layout at narrow widths
- Visible focus states
- Keyboard operation
- The approved N0JCG logo asset
- A single, clear product title

## Maintenance checklist

When reusing this header in another N0JCG application:

1. Keep the approved logo and dark navy treatment.
2. Change only the product title and product-specific status behavior.
3. Preserve the trial/registration behavior when the product uses licensing.
4. Keep `aria-expanded`, `aria-controls`, and accessible labels synchronized.
5. Update the JavaScript cache-buster whenever header behavior changes.
6. Test desktop and narrow-screen layouts before release.

## Source files

- Header markup: `web/index.html`
- Shared brand styling: `web/brand.css`
- Application styling: `web/app.css`
- Header state and event handlers: `web/app.js`
