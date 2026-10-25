SHELL := /bin/bash

.PHONY: all deb windows zip test test-deb test-windows clean

all: deb windows zip

# Linux: build the .deb in ubuntu:22.04 (runs the unit tests first), then stage the release
deb:
	scripts/build-deb.sh
	@echo "== Linux release =="
	@cat releases/fankata_*_amd64.deb.sha256

# Windows: PyInstaller + Inno Setup under Wine, then stage the release
windows:
	scripts/build-windows.sh
	@echo "== Windows release =="
	@cat releases/Fankata-*-setup.exe.sha256

# Source archive: everything in the repo not excluded by .gitignore
zip:
	mkdir -p releases
	rm -f releases/source.zip
	@sed -e 's/\#.*//' -e '/^[[:space:]]*$$/d' -e 's|^/||' -e 's|/$$||' .gitignore \
		| while read -r p; do echo "$$p"; echo "$$p/*"; done > releases/.zip-excludes; \
	zip -rq releases/source.zip . -x@releases/.zip-excludes; \
	rm -f releases/.zip-excludes; \
	echo "== Source archive =="; \
	unzip -l releases/source.zip | tail -1

# Unit tests on this machine; the install tests need Docker (and, for Windows, the test VM)
test:
	PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests

test-deb:
	scripts/test-deb.sh

test-windows:
	scripts/test-windows-vm.sh

clean:
	rm -rf build/windows releases/*
