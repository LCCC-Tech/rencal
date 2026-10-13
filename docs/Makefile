SPHINXOPTS    ?=
SPHINXBUILD   ?= python -m sphinx.cmd.build
SOURCEDIR     = source
BUILDDIR      = build

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile interrogate

%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

interrogate:
	cd .. && uv run python -m interrogate rencal --fail-under 0 --style google --verbose
