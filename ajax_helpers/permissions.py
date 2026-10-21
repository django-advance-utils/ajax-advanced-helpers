from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.utils.html import escape
from django.utils.module_loading import import_string

PERMISSION_DENIED_MESSAGE = 'You do not have permission to do this.'


def is_permitted(request, kind, name, obj=None):
    path = getattr(settings, 'DJANGO_ADVANCED_PERMISSION_CHECK', None)
    if not path:
        return True
    return bool(import_string(path)(request, kind, name, obj))


def refusal(view, kind, name):
    check = getattr(view, 'check_ajax_permission', None)
    allowed = check(kind, name) if check else is_permitted(getattr(view, 'request', None), kind, name, view)
    if allowed:
        return None
    denied = getattr(view, 'refuse_ajax', None)
    if denied:
        return denied(kind, name)
    return denied_response(kind)


def denied_response(kind):
    if kind == 'tooltip':
        return HttpResponse(escape(PERMISSION_DENIED_MESSAGE))
    return JsonResponse([{'function': 'message', 'text': PERMISSION_DENIED_MESSAGE}], safe=False)
