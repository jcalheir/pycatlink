# CatLink Library and Home Assistant Integration

[![My Home Assistant](https://img.shields.io/badge/Home%20Assistant-%2341BDF5.svg?style=flat&logo=home-assistant&label=My)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EuleMitKeule&repository=pycatlink&category=integration)

![PyPI - Version](https://img.shields.io/pypi/v/pycatlink?logo=python&logoColor=green&color=blue)
![GitHub License](https://img.shields.io/github/license/eulemitkeule/pycatlink)
![GitHub Sponsors](https://img.shields.io/github/sponsors/eulemitkeule?logo=GitHub-Sponsors)

[![Code Quality](https://github.com/EuleMitKeule/pycatlink/actions/workflows/quality.yml/badge.svg)](https://github.com/EuleMitKeule/pycatlink/actions/workflows/quality.yml)
[![Publish](https://github.com/EuleMitKeule/pycatlink/actions/workflows/publish.yml/badge.svg)](https://github.com/EuleMitKeule/pycatlink/actions/workflows/publish.yml)

---

## About this fork (jcalheir/pycatlink)

Adds **email-based CatLink account** login (`login/email`) — enter the email in
the "Phone number or email" field. The library change is proposed upstream; until
a pycatlink release includes it, `custom_components/catlink/email_login.py` adds it
on top of the PyPI library (no-op once upstream supports it). A weekly workflow
merges upstream changes into this fork.
