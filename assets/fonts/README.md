# Fonts

Cyrillic-capable fonts for PDF generation — RFP §10.3, §627.

Place `.ttf` / `.otf` files here. The Dockerfile copies this directory into
`/usr/share/fonts/truetype/kinder/` and runs `fc-cache`, so WeasyPrint can
reference them via `@font-face` in CSS.

**Do not rely on system fonts.** The container is minimal and the host's fonts
are not available. If this directory is empty, Mongolian Cyrillic will render
as `□□□` in generated PDFs.

Recommended: a font with full Cyrillic coverage and a redistributable licence
(Noto Sans, DejaVu Sans, Roboto). Record the licence of whatever is added here
— RFP §19 requires a list of licensed materials.
