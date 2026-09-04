from django.conf import settings


def app_info(request):
    return {
        'app_version': getattr(settings, 'APP_VERSION', ''),
        'app_author': getattr(settings, 'APP_AUTHOR', ''),
        'mkdocs_base_url': getattr(settings, 'MKDOCS_BASE_URL', ''),
    }
