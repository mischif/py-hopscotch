################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                               (C) 2019 Mischif                               #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

COV_OPTIONS="--cov=hopscotchdict --cov-report xml --cov-report term-missing --cov-config setup.cfg"

.PHONY: test ci-test build

clean:
	rm -rf .coverage coverage.xml .eggs/ .hypothesis/ .pytest_cache/ *egg-info/ dist/ build/
	find . -name __pycache__ -exec rm -rf {} +
	find . -name *.pyc -exec rm -rf {} +

test:
	python -B setup.py test

ci-test:
	HYPOTHESIS_PROFILE=ci python setup.py test --addopts ${COV_OPTIONS}

build:
	python setup.py build sdist bdist_wheel
