from django.conf import settings


def branding(request):
    """Make branding settings available in all templates."""
    return {
        'brand_name': getattr(settings, 'BRAND_NAME', 'FaceID Portal'),
        'brand_company': getattr(settings, 'BRAND_COMPANY', ''),
        'brand_accent': getattr(settings, 'BRAND_ACCENT_COLOR', '#00d4ff'),
    }
