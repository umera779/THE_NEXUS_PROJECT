from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

templates = Jinja2Templates(env=Environment(
    loader=FileSystemLoader("app/templates"),
    auto_reload=True,
))