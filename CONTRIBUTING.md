# Contributing

Thank you for helping improve Django Content Studio. This guide covers the
development setup and how to propose a change.

## Development setup

The backend is a Django app managed with Poetry; the admin's frontend is a
React application in `frontend/`, built into the package's static files.

```bash
git clone https://github.com/dwarsbit/djangocontentstudio.git
cd djangocontentstudio

# Backend
poetry install
poetry run pytest

# Frontend
cd frontend
npm install
npm test
npm run dev
```

The `demo/` project runs the admin against example models; see
[demo/README.md](demo/README.md). The documentation website lives in
`website/`; see [website/README.md](website/README.md).

## Proposing a change

1. Fork the repository and create a branch for your change.
2. Make the change, with tests: `poetry run pytest` for the backend,
   `npm test` in `frontend/` for the frontend.
3. Format the code: `black` for Python, `prettier` for the frontend.
4. Update the documentation when behavior changes, following the
   [writing style guide](website/STYLE.md), and add a line to the
   [changelog](CHANGELOG.md).
5. Open a pull request that explains what changed and why.

## Translations

The admin ships in English, Dutch, German, French, Spanish, Italian and
Brazilian Portuguese. Its text lives in two places, and every language has
every string in both:

- **The admin's interface**: `frontend/public/locales/<locale>/translation.json`,
  one file per language (`pt-BR` for Brazilian Portuguese). English is the
  source. Plurals use i18next's suffixes: `_one` and `_other`, plus `_many`
  for French, Spanish, Italian and Portuguese.
- **Strings from Django** (field labels, errors, emails):
  `content_studio/locale/<locale>/LC_MESSAGES/django.po` (`pt_BR`), with the
  compiled `django.mo` next to it. Both are committed.

When you add or change a string, add it to every language. If you cannot
translate it, ask in the pull request. After changing Python or template
strings, update and compile the catalogs (this needs GNU gettext):

```bash
cd content_studio
django-admin makemessages --all --no-obsolete
django-admin compilemessages
```

`tests/test_languages.py` fails when a language misses a string, has one
English no longer has, or uses other placeholders than English.

To add a language:

1. Add it to `LANGUAGES` in `content_studio/languages.py`, with its own
   name, and its plural forms to `PLURAL_CATEGORIES` in
   `tests/test_languages.py`.
2. Copy `frontend/public/locales/en/translation.json` to the new locale and
   translate it.
3. In `content_studio`, run `django-admin makemessages -l <locale>`,
   translate the `.po` file and run `django-admin compilemessages`.
4. If the date picker should name months and days in it, add its locale to
   `frontend/src/lib/languages.ts`.
5. List it in `scripts/check_wheel.py` and on the docs' Languages page.

## Questions and security

Ask questions in [GitHub Discussions](https://github.com/dwarsbit/djangocontentstudio/discussions).
Report security problems privately, as described in [SECURITY.md](SECURITY.md).
