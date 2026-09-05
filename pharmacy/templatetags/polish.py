"""Polish-language copy helpers for templates.

Django's built-in `pluralize` picks between two forms; Polish uses three. This
project ships no locale catalogues and no `LocaleMiddleware`, so
`{% blocktranslate %}`'s plural machinery is not available either — hence a
filter rather than i18n.

Screens that can phrase a count as a label followed by a number
("Liczba opakowań: 3") should keep doing that and skip this entirely: that
shape agrees for every value and needs no rule. This exists for the copy that
genuinely reads better as a sentence.
"""

from django import template

register = template.Library()


@register.filter
def plural_pl(count: object, forms: str) -> str:
    """Pick a Polish plural form for `count` from a "one,few,many" triple.

    The rule Polish actually uses: 1 takes the singular; numbers ending in
    2, 3 or 4 take the "few" form — *except* the teens (12, 13, 14), which
    behave like every other value and take "many". 0 takes "many" too.

    Not cosmetic. "2 opakowań" reads as broken Polish to every user of this
    app, and a two-form `pluralize` produces exactly that for 2, 3 and 4.
    """
    parts = forms.split(',')
    # A filter is not the place to raise on a template author's typo, so an
    # unusable value falls back rather than 500-ing the page. This covers the
    # form-spec argument too: a malformed "one,few,many" triple is the same
    # kind of typo as a bad count, and unpacking it must not raise either.
    if len(parts) != 3:
        return forms
    one, few, many = parts
    try:
        n = abs(int(count))  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return many
    if n == 1:
        return one
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return few
    return many
