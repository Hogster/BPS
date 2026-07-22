# Contribution guidelines

Contributing to this project should be as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Github is used for everything

Github is used to host code, to track issues and feature requests, as well as accept pull requests.

Pull requests are the best way to propose changes to the codebase.

1. Fork the repo and create your branch from `main`.
2. If you've changed something, update the documentation.
3. Test your contribution (see [Testing](#testing)).
4. Issue that pull request!

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using Github's [issues](../../issues)

GitHub issues are used to track public bugs.
Report a bug by [opening a new issue](../../issues/new/choose); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People _love_ thorough bug reports. I'm not even kidding.

## Testing

The backend has a unit-test suite under [`tests/`](./tests) that runs against
the real integration modules with the Home Assistant runtime stubbed out (see
`tests/conftest.py`), so it needs no HA install — only the numeric libraries
the positioning/geometry code uses.

From the repository root:

```console
$ pip install -r requirements_test.txt
$ pytest tests/ -q
```

CI runs the same suite plus a byte-compile of the integration and a
`node --check` of the frontend on every push and pull request
(`.github/workflows/test.yaml`), alongside Hassfest/HACS validation
(`.github/workflows/validate.yaml`). Please keep the suite green and add tests
for new positioning, calibration, or election logic.

For end-to-end testing in a running Home Assistant, the
[integration_blueprint template](https://github.com/custom-components/integration_blueprint)
provides a VS Code dev-container with a standalone HA instance.

## License

By contributing, you agree that your contributions will be licensed under its MIT License.
