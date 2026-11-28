"""
The demo's tiny public site: an article's page and a contact form. Drafts
show with a preview link (see content_studio.previews), live articles to
everyone. The contact form is behind the captcha
(content_studio.contrib.captcha).
"""

from django import forms
from django.shortcuts import get_object_or_404, render
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override

from content_studio.contrib.captcha.forms import CAPTCHA_CSP, CaptchaField
from content_studio.previews import previewable

from .models import Article


def article_detail(request, slug):
    articles = previewable(request, Article.objects.all())
    lookup = {"pk": int(slug)} if slug.isdigit() else {"slug": slug}
    article = get_object_or_404(articles, **lookup)

    return render(request, "blog/article.html", {"article": article})


class ContactForm(forms.Form):
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea)
    captcha = CaptchaField()


@csp_override(
    {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, *CAPTCHA_CSP["script-src"]],
        "style-src": [CSP.SELF, CSP.NONCE, *CAPTCHA_CSP["style-src"]],
        "worker-src": [*CAPTCHA_CSP["worker-src"]],
        "img-src": [CSP.SELF, *CAPTCHA_CSP["img-src"]],
    }
)
def contact(request):
    form = ContactForm(request.POST or None)
    sent = request.method == "POST" and form.is_valid()

    return render(
        request,
        "blog/contact.html",
        {"form": ContactForm() if sent else form, "sent": sent},
    )
