# Embedding the Variance Generator on the website

## What this tool is
**FP&A Variance Commentary Generator** — a Streamlit (Python) web app. The user uploads
Budget and Actuals CSVs (optionally prior-period CSVs too) and the tool produces CFO-ready
variance commentary using the Anthropic API, with charts and an Excel export. It also ships
with a built-in sample dataset so visitors can try it without their own data.

It is **not** HTML/JS and cannot be copied into the page source. It runs as a hosted app and
is shown on the website via an `<iframe>`.

## Deployed app URL
> Replace this placeholder with the real Streamlit Cloud URL after deploying:
```
https://REPLACE-ME.streamlit.app
```

## How to embed it
Drop this into the website's HTML where the tool should appear. The wrapper makes it
responsive and gives it a sensible height (Streamlit apps are tall — 900px+ works well).

```html
<section id="variance-generator" style="width:100%; max-width:1100px; margin:2rem auto;">
  <iframe
    src="https://REPLACE-ME.streamlit.app/?embed=true"
    title="FP&A Variance Commentary Generator"
    style="width:100%; height:900px; border:1px solid #e2e2e2; border-radius:12px;"
    loading="lazy"
    allow="clipboard-write">
  </iframe>
</section>
```

### Notes
- The `?embed=true` query param tells Streamlit to hide its top menu/footer chrome so it
  looks like part of the page rather than a standalone app. (`&embed_options=...` can further
  tweak it — e.g. `embed_options=light_theme`.)
- Adjust `height` to taste; this app is long, so don't go below ~800px or users will scroll
  inside the iframe.
- If a "launch in full screen" link is preferred over an inline embed, just link to the
  bare URL (without `?embed=true`) instead of using an iframe.

## Alternative (only if an iframe is unacceptable)
Rebuilding the tool as native frontend code would mean rewriting the Python/Anthropic logic
in JavaScript and routing API calls through a backend to keep the API key secret. That's a
real project, not an embed. The iframe is the recommended path.
