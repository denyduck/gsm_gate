from django.conf import settings

from . import access


def app_info(request):
    return {
        'app_version': getattr(settings, 'APP_VERSION', ''),
        'app_author': getattr(settings, 'APP_AUTHOR', ''),
        'mkdocs_base_url': getattr(settings, 'MKDOCS_BASE_URL', ''),
        # Třetí úroveň práv (super admin > admin > user) - viz access.is_admin.
        # Admin skupina má v appce prakticky stejná práva jako superuser,
        # jen bez samotného is_superuser flagu.
        'is_admin': access.is_admin(getattr(request, 'user', None)),
    }
