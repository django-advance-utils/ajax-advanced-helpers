import json
from django import template
from django.templatetags.static import static
from django.urls import reverse
from django.utils.safestring import mark_safe
from ..utils import random_string
from ..html_include import html_include
register = template.Library()

# The render context key under which lib_include records the libraries a render has written out.
LIBRARIES_INCLUDED = 'ajax_helpers_libraries_included'


@register.simple_tag(takes_context=True)
def lib_include(context, *args, **kwargs):
    """
    The script and stylesheet tags for the named libraries (see html_include).

    Each library is written once per render. A later request for one already written writes nothing, whether it
    comes from the template this one extends, from a template it includes, or through a second package that also
    contains the library. A second copy is wasted at best (Fancytree notices one and ignores it). At worst it breaks
    the page: a second jQuery replaces the first and drops every plugin registered on it.

    The scope is one render: the template rendered, the ones it extends and the ones it includes. A fragment
    rendered on its own, such as a modal body or an ajax response, includes its libraries again.
    """
    request = context.get('request')
    legacy = False
    if request:
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if 'Trident' in user_agent or 'MSIE' in user_agent:
            legacy = True
    included = _libraries_included(context)
    include_str = ''
    if not args:
        include_str = html_include(cdn=kwargs.get('cdn'),
                                   module=kwargs.get('module'),
                                   legacy=legacy,
                                   version=kwargs.get('version'),
                                   included=included)
    for a in args:
        include_str += html_include(a,
                                    cdn=kwargs.get('cdn'),
                                    module=kwargs.get('module'),
                                    legacy=legacy,
                                    version=kwargs.get('version'),
                                    included=included)
    return mark_safe(include_str)


def _libraries_included(context):
    """
    The set of SourceBase classes this render has written out, or None when context is not a template context.

    It is kept at the root of the render context. An included template gets a layer of its own above that root,
    but everything in one Template.render call shares the root: the template rendered, the ones it extends and
    the ones it includes, with or without only. Django's include tag keeps its per-render template cache there too.
    """
    render_context = getattr(context, 'render_context', None)
    if render_context is None:
        return None
    return render_context.dicts[0].setdefault(LIBRARIES_INCLUDED, set())


@register.simple_tag
def init_ajax():
    return mark_safe(f'<script src="{static("ajax_helpers/ajax_helpers.js")}"></script>')


def determine_css_class(bootstrap_style, css_class):
    if css_class:
        return css_class
    return 'btn ' + ' '.join(['btn-' + s.strip() for s in bootstrap_style.split(',')])


@register.simple_tag
def post_json_js(url_name=None, url_args=None, blob=False, **kwargs):
    json_data = {'data': kwargs}
    if url_name:
        json_data['url'] = reverse(url_name, args=url_args)
    if blob:
        json_data['response_type'] = 'blob'
    return mark_safe(f'ajax_helpers.post_json({json.dumps(json_data)})')


@register.simple_tag
def button_javascript(button_name, url_name=None, url_args=None, blob=False, **kwargs):
    return post_json_js(button=button_name, url_name=url_name, url_args=url_args, blob=blob, **kwargs)


@register.simple_tag
def ajax_button(text, name, bootstrap_style='primary', css_class=None, **kwargs):
    return mark_safe(f'''<button class="{determine_css_class(bootstrap_style, css_class) }"''' 
                     f'''onclick='{button_javascript(name, **kwargs) }'>{ text }</button>''')

@register.simple_tag
def ajax_method_button(text, method, bootstrap_style='primary', css_class=None, **kwargs):
    return mark_safe(f'''<button class="{determine_css_class(bootstrap_style, css_class) }"''' 
                     f'''onclick='{post_json_js(ajax_method=method, **kwargs) }'>{ text }</button>''')


@register.simple_tag
def send_form(form_id, **kwargs):
    kwargs.update({"form_id": form_id})
    return f'''ajax_helpers.send_form("{form_id}", {json.dumps(kwargs)})'''


@register.simple_tag
def send_form_button(text, form_id, bootstrap_style='primary', css_class=None, **kwargs):
    return mark_safe(f'''<button class="{ determine_css_class(bootstrap_style, css_class) }"''' 
                     f'''onclick='{send_form(form_id, **kwargs) }'>{ text }</button>''')


@register.inclusion_tag('ajax_helpers/upload_file.html')
def upload_file(text='Upload File', bootstrap_style='primary', css_class=None, drag_drop=None, width=None, height=None, progress=False):
    return {
        'id': random_string(),
        'text': text,
        'css_class': determine_css_class(bootstrap_style, css_class),
        'drag_drop': drag_drop,
        'width': width,
        'height': height,
        'progress': progress,
    }


@register.simple_tag
def tooltip_init(selector, function_name, placement='', template=''):
    return mark_safe(f"<script>ajax_helpers.tooltip('{selector}', '{function_name}', "
                     f"'{placement}', '{template}')</script>")


@register.inclusion_tag('ajax_helpers/ajax_timer.html')
def ajax_timer(name, interval_ms):
    return {
        'name': name,
        'interval': interval_ms
    }
