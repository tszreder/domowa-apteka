---
title: "How does one base.html become every page, and where does the styling come from?"
slug: django-templates-and-css
date: 2026-08-05
tags: [django, templates, static-files, css, web-fundamentals]
classification: mixed
prerequisites: [static-files-collectstatic-and-whitenoise]
---

# How does one `base.html` become every page, and where does the styling come from?

## Why this came up

Phase 1 of `context/changes/household-accounts-and-invites/plan.md` created
`templates/base.html` and had every page in the `households` app — `landing.html`,
`signup.html`, `household_detail.html`, and (Phase 5) `item_list.html` — declare
`{% extends "base.html" %}` at the top and fill in just a `{% block content %}`. That's two
things worth understanding on their own: how Django assembles one page out of two files, and
where `<link rel="stylesheet" href="{% static 'css/pico.min.css' %}">` in that base template
actually resolves to a real file on disk.

## Builds on

[static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md)
already explained *why* `collectstatic` exists and how WhiteNoise serves the result in
production. This doc assumes that and covers the piece that doc didn't: how `{% static %}`
resolves a path *before* `collectstatic` has run anything (i.e. in local dev), and template
inheritance, which is unrelated to static files but shows up in the same base template.

## The concept, from the ground up

### Template inheritance: one shared skeleton, many filled-in pages

Every page in this project's `households/templates/households/` directory starts the same way:

```django
{% extends "base.html" %}

{% block title %}{{ household.name }} — Domowa Apteka{% endblock %}

{% block content %}
    <h1>{{ household.name }}</h1>
    ...
{% endblock %}
```

`templates/base.html` defines the full HTML document once — `<html>`, `<head>` with the
stylesheet links, a `<header>` with the nav/login state, a `<main>` — and marks two spots as
*replaceable* with `{% block title %}...{% endblock %}` and `{% block content %}{% endblock %}`.
A child template's `{% extends "base.html" %}` says "start from that skeleton"; anything the
child puts inside a matching `{% block %}` tag overwrites just that section, and everything
else — the `<head>`, the stylesheet links, the header/nav markup — is inherited untouched. This
is why adding Phase 5's `item_list.html` required writing only an `<h1>` and a paragraph, not a
full HTML document: the shared shell already exists in exactly one place, so a change to it (a
new nav link, a new meta tag) automatically applies to every page that extends it, with zero
per-page edits.

Django resolves `"base.html"` in `{% extends %}` the same way it resolves the template name
passed to `render()` in a view: it searches, in order, the directories listed in
`TEMPLATES[0]['DIRS']` (`settings.py` sets this to `[BASE_DIR / 'templates']` — the
project-level shared folder) and then, because `'APP_DIRS': True`, every installed app's own
`<app>/templates/` directory. That's why `households/templates/households/landing.html` is
namespaced under a `households/` subfolder inside the app's own template directory — with
`APP_DIRS` search enabled, a flat `templates/landing.html` inside two different apps would
collide; nesting each app's templates under its own name avoids that.

### `{% static %}`: a template tag, not a hardcoded path

`base.html`'s stylesheet link is not a literal path:

```django
{% load static %}
...
<link rel="stylesheet" href="{% static 'css/pico.min.css' %}">
```

`{% load static %}` brings in Django's `staticfiles` template tags; `{% static 'css/pico.min.css' %}`
then asks Django's staticfiles *finders* to locate a file at that relative path and render the
correct URL for it. In local dev (`DEBUG=True`, `runserver`), the finder searches
`STATICFILES_DIRS` (this project's project-level `static/` folder, where
`static/css/pico.min.css` actually lives) plus every installed app's own `static/` subfolder,
and Django itself serves whatever it finds — no `collectstatic` run required, which is why
static assets "just work" while developing locally. In production, as
[static-files-collectstatic-and-whitenoise.md](static-files-collectstatic-and-whitenoise.md)
covers, `collectstatic` has already copied everything into `STATIC_ROOT` ahead of time and
WhiteNoise serves it from there — but the `{% static %}` tag in the template doesn't change
between the two; only what answers the request does.

### Where the actual look comes from: a vendored classless stylesheet

`base.html` loads two stylesheets, in this specific order:

```django
<link rel="stylesheet" href="{% static 'css/pico.min.css' %}">
<link rel="stylesheet" href="{% static 'css/app.css' %}">
```

Pico first, `app.css` second, so `app.css`'s rules can override Pico's for anything this
project wants to change — CSS applies rules in source order when specificity ties, so whichever
stylesheet loads last wins a direct conflict. Pico is a **classless** framework: it styles bare
HTML elements (`h1`, `form`, `button`, `nav`) by tag name, so `households/templates/*.html`
never needs a single `class="..."` attribute to look reasonable — semantic markup alone is
enough. Both files are committed into `static/css/` rather than loaded from a CDN, so the app
has zero external runtime dependency and local dev works offline.

This project already has flashcards covering the classless-vs-utility-first CSS trade-off in
more depth (why classless is cheap to swap out, what a build step like Tailwind's would add,
why "everything looks the same" is much less of a risk with a niche classless framework than
with something as dominant as Bootstrap once was) — that reasoning isn't repeated here.

## In terms you already know

| This project's concept | What it's like in your world |
| --- | --- |
| `{% extends %}` / `{% block %}` template inheritance | A **Power BI report theme + a shared master page layout** — the theme/layout defines the shell once (fonts, header, nav), and each individual report page only supplies the part that's genuinely different, inheriting everything else automatically. |
| `TEMPLATES[0]['DIRS']` + per-app `APP_DIRS` search order | ADF's search path across a **global "Shared" folder plus each pipeline's local resources** — a name resolves by checking the shared location first, then the calling pipeline's own folder. |
| `{% static 'css/pico.min.css' %}` resolving to a real file via a finder, not a hardcoded URL | A **Power BI report referencing a theme file by logical name**, resolved to wherever that asset actually lives (workspace, external URL) at render time, rather than the report hardcoding a path. |
| Classless CSS styling elements by tag name, no markup changes needed | The **default Power BI theme** applying consistent formatting to every visual of a given type automatically, without you setting per-visual formatting — until you need something specific enough to override it. |

## What's universal vs. what's specific to this project's choices

**True for any templating system, not just Django's:**
- Sharing one layout and filling in per-page differences (rather than duplicating the full
  HTML document per page) is the point of template inheritance in essentially every web
  framework — Jinja2, Rails' ERB layouts, ASP.NET Razor's `_Layout.cshtml` all follow the same
  shape.
- Referencing static assets through a resolvable name/tag rather than a hand-typed path — so
  the actual served location can differ between dev and prod without touching every template —
  is standard practice, not a Django peculiarity.
- CSS's core mechanism (later, equally-specific rules override earlier ones; more specific
  selectors override less specific ones) is a CSS-language rule, not framework-specific.

**Specific because this project picked Django + a classless CSS framework:**
- The exact tag names (`{% extends %}`, `{% block %}`, `{% static %}`, `{% load static %}`) and
  the `TEMPLATES` / `STATICFILES_DIRS` settings are Django's own template and staticfiles
  systems — a different framework would use different syntax for the same underlying ideas.
- `APP_DIRS: True` searching every installed app's own `templates/` folder automatically is a
  Django convention; frameworks without an "app" concept just have one templates directory.
- Choosing a classless framework (Pico) over a utility-first one (Tailwind) or hand-rolled CSS
  is this project's own trade-off, made for a small number of screens with no design-system
  requirement — a larger or more design-driven project might reasonably choose differently.

## Go deeper

- [Django Template Language — RealPython](https://realpython.com/django-templates-tags-filters/) —
  covers `{% extends %}`/`{% block %}` and tag/filter basics with runnable examples, no prior
  web-dev background assumed.
- [Django official docs: Template inheritance](https://docs.djangoproject.com/en/5.2/ref/templates/language/#template-inheritance)
  and [The `static` template tag](https://docs.djangoproject.com/en/5.2/ref/templates/builtins/#std-templatetag-static) —
  the authoritative reference for both mechanisms covered here.

## Quick recap

**Q: What does `{% extends "base.html" %}` actually do?**
A: Tells Django "render `base.html`'s full structure, but substitute my content into any
`{% block %}` I also define" — the child template supplies only the parts that differ from the
shared shell.

**Q: Why is `landing.html` at `households/templates/households/landing.html` instead of just `households/templates/landing.html`?**
A: Because `APP_DIRS: True` searches every installed app's `templates/` folder by the same
relative name — nesting under `households/` avoids a filename collision with some other app
that also happens to have a `landing.html`.

**Q: Does `{% static 'css/pico.min.css' %}` point at a hardcoded URL?**
A: No — it's a template tag that asks Django's staticfiles finders to locate the actual file
and emit the correct URL, which differs between local dev (served directly) and production
(served from `STATIC_ROOT` by WhiteNoise, after `collectstatic`).

**Q: Why does `app.css` load after `pico.min.css` in `base.html`, not before?**
A: CSS resolves ties in source order — the stylesheet loaded last wins on a direct conflict, so
loading `app.css` second is what lets it override Pico's defaults for anything this project
wants to change.

**Q: When would you reach for a second `{% block %}` instead of just adding more content inside `{% block content %}`?**
A: Whenever a section needs to be independently overridable *and* isn't always in the same
place — this project's `{% block title %}` is a separate block precisely because it belongs in
`<head><title>`, not inside `<main>` where `{% block content %}` renders.
