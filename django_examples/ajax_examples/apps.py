from show_src_code.apps import PypiAppConfig


class AjaxConfig(PypiAppConfig):
    default = True
    name = 'ajax_examples'
    pypi = 'ajax-advanced-helpers'
    urls = 'ajax_examples.urls'
