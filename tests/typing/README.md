# Type hint checks

Content Studio ships its type hints (`content_studio/py.typed`), so a hint
that is too narrow gives projects false errors in mypy or Pyright.
`public_api.py` is typical project code against the public API; CI's
typing job checks it with both:

```bash
poetry run mypy --config-file tests/typing/mypy.ini tests/typing/public_api.py
poetry run pyright -p tests/typing
```

Errors inside `content_studio` itself are not reported, as for an
installed package: only the project code counts. When a public hint
changes, or a pattern from the docs is not covered yet, add it to
`public_api.py`. The file is never run and pytest does not collect it.
