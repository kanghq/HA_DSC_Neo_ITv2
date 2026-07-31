# Brand images

This directory contains the integration's icon and logo, served by Home
Assistant 2026.3+ from the local custom integration. **Before HA 2026.3**
brand images had to be submitted via a PR to the
[home-assistant/brands](https://github.com/home-assistant/brands)
repository; the local `brand/` directory removes that requirement for
custom integrations.

See: <https://developers.home-assistant.io/docs/core/integration/brand_images/>

## Files

| File                  | Required | Size (px)       | Notes                              |
| --------------------- | -------- | --------------- | ---------------------------------- |
| `icon.png`            | yes      | 256 x 256       | Square, transparent background     |
| `icon@2x.png`         | optional | 512 x 512       | hDPI variant                       |
| `dark_icon.png`       | optional | 256 x 256       | Optimised for dark backgrounds     |
| `dark_icon@2x.png`    | optional | 512 x 512       | hDPI dark variant                  |
| `logo.png`            | optional | landscape, short side 128-256 | Used in config-flow header |
| `logo@2x.png`         | optional | landscape, short side 256-512 | hDPI variant       |
| `dark_logo.png`       | optional | landscape       | Dark-mode variant                  |
| `dark_logo@2x.png`    | optional | landscape       | hDPI dark variant                  |

PNG format with transparency is preferred. Each variant is a light or
dark, 1x or 2x rendering of the same source artwork, cropped square for
the icons and landscape for the logos.

## Trademark notice

The DSC and PowerSeries Neo names and marks shown in these images are
trademarks of their respective owners (Tyco / Johnson Controls). They
are used here solely to identify the product this integration
communicates with. This is an unofficial, community-developed
integration and is **not affiliated with, endorsed by, or sponsored
by** DSC, Tyco, or Johnson Controls. If the trademark holder requests
removal, replace the contents of this directory with neutral
placeholder artwork.

If this integration is ever submitted to Home Assistant Core, remove
this directory and open a PR against the
[brands repository](https://github.com/home-assistant/brands) instead.
