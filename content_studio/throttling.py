from rest_framework.settings import api_settings


class ClientIPMixin:
    """
    Identify throttled clients by an address they cannot choose.

    DRF's default identity is the raw X-Forwarded-For header when
    REST_FRAMEWORK["NUM_PROXIES"] is unset, so a client sending a
    different header per request gets a fresh bucket each time. Without
    NUM_PROXIES the connection's REMOTE_ADDR is used instead; with it,
    DRF picks the address the configured proxies added.
    """

    def get_ident(self, request):
        if api_settings.NUM_PROXIES is None:
            return request.META.get("REMOTE_ADDR")

        return super().get_ident(request)


def client_ip(request):
    """
    The client's IP address by the same rule as the throttles
    (ClientIPMixin): REMOTE_ADDR, or with NUM_PROXIES the address the
    proxies added. None when it is not a valid address.
    """
    import ipaddress

    from rest_framework.throttling import BaseThrottle

    request = getattr(request, "_request", request)

    if api_settings.NUM_PROXIES is None:
        address = request.META.get("REMOTE_ADDR")
    else:
        address = BaseThrottle().get_ident(request)

    try:
        return str(ipaddress.ip_address((address or "").strip()))
    except ValueError:
        return None


def parse_rate(rate):
    """
    A rate such as "10/min" or "20/hour" as (count, seconds), the way
    DRF reads its throttle rates: the period is its first letter.
    """
    count, period = rate.split("/")
    seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[period.strip()[0]]

    return int(count), seconds
