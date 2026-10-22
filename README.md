# DialoStack website

This branch holds only the project website, served by GitHub Pages at
**https://aquintan4.github.io/DialoStack/**. The source code and documentation
live on [`main`](https://github.com/aquintan4/DialoStack).

| File | Purpose |
|------|---------|
| `index.html` | The landing page: self-contained HTML, CSS and JS, no build step |
| `assets/` | Logo, favicon and the social preview image (`og-image.png`, 1200×630) |
| `assets/media/` | Recordings of the real GUI (`.mp4` + `.webm`, loaded on demand) and screenshots (`.webp`, dark and light) |
| `sitemap.xml`, `robots.txt` | Search engine indexing |
| `.nojekyll` | Serve files as they are, without Jekyll processing |

To preview locally: `python3 -m http.server` in this directory, then open http://localhost:8000.
After changing the page, update `<lastmod>` in `sitemap.xml`.

The recordings are real dialogues driven in the GUI against a running engine (Ollama, `qwen3.5:9b`). Re-record them when the GUI changes noticeably, so the site keeps showing the product as it is.
