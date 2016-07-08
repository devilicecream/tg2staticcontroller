# tg2staticcontroller
A TurboGears2 Controller used to serve static files in a easy way.
It is more flexible then TG2's standard way to serve static files, because it can be plugged at any given path, and can even be used with the authentication and validation systems.

## Usage

```python
from myapp.lib.base import BaseController
from myapp.lib.staticcontroller import StaticController

class RootController(BaseController):
  docs = StaticController('docs')
```
