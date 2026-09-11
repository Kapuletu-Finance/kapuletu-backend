from jinja2 import Environment, FileSystemLoader
import os
import datetime

TEMPLATE_DIR = os.path.dirname(__file__)
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

def render_email_template(template_name: str, **context) -> str:
    from common.config import get_config
    template = env.get_template(template_name)
    context['year'] = datetime.datetime.now().year
    context['frontend_url'] = get_config().FRONTEND_URL.rstrip('/')
    return template.render(**context)
