################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

.POSIX:

CI_OPTIONS="--cov-report xml --hypothesis-profile ci"

.PHONY: ci-test clean release test typecheck

clean:
	rm -rf .coverage coverage.xml .eggs/ .hypothesis/ .pytest_cache/ *egg-info/ dist/ build/
	find . -name __pycache__ -exec rm -rf {} +
	find . -name *.pyc -exec rm -rf {} +

test:
	python -B setup.py test

ci-test:
	python setup.py test --addopts ${CI_OPTIONS}

release:
	python -m pep517.build -sb .

typecheck:
	mypy --python-version 3.6 --pretty --strict --strict-optional --warn-no-return --warn-unreachable --disallow-redefinition src/
