.PHONY: install lint

STEP_SRC_PATTERN=step_*.py

# install lambda function dependencies
install:
	pipenv --python $(which python3) install

# lint step source files
lint:
	pipenv run flake8 ${STEP_SRC_PATTERN}
