### Rndopsapp

RND automation software

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app rndopsapp
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/rndopsapp
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit




<!-- ============================================================= -->
<!-- Clinton-need -->

rm -rf node_modules package-lock.json

npm cache clean --force

npm install

npm audit

npm audit fix --force

npm install --save-dev ts-node@latest



=======================================================
Clinton/feature/universal-registration-fix-V2


git branch -a Clinton/feature/universal-registration-optionsing-fix-touba
