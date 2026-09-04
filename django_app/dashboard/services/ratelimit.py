"""Jednoduchý cache-based počítač selhání pro rate limiting (API ingest
token, login lockout). Používá Django cache framework - u výchozího
LocMemCache je počítadlo per-proces (3 gunicorn workeři = fakticky až
3x vyšší efektivní limit), což je pro tuhle velikost nasazení přijatelný
kompromis bez potřeby Redis/Memcached."""

from django.core.cache import cache


def get_failure_count(key):
    return cache.get(key, 0)


def register_failure(key, window_seconds):
    count = cache.get(key, 0) + 1
    cache.set(key, count, window_seconds)
    return count


def reset_failures(key):
    cache.delete(key)
