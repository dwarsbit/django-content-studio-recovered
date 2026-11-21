from django.utils.cache import patch_cache_control

from . import get_param

__all__ = ["PreviewMiddleware"]


class PreviewMiddleware:
    """
    Keeps preview pages private: a response to a request with a preview
    token is never cached by a CDN or the browser, never indexed, and
    sends no Referer, so the token stays out of caches, search results
    and other sites' logs. Set on every request that carries the
    parameter, valid token or not.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if get_param() in request.GET:
            patch_cache_control(response, private=True, no_store=True, max_age=0)
            response["X-Robots-Tag"] = "noindex, nofollow"
            response["Referrer-Policy"] = "no-referrer"

        return response
