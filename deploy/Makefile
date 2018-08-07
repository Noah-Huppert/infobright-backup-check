.PHONY: install lint

DEPLOY_SCRIPT_SRC=deploy.py

# install deploy script dependencies
install:
	pipenv install

# lint deploy script
lint:
	pipenv run flake8 "${DEPLOY_SCRIPT_SRC}"
