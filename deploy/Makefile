.PHONY: install lint

DEPLOY_SCRIPT_SRC=deploy.py
GH_RELEASE_SCRIPT_SRC=create_gh_release.py

# install deploy script dependencies
install:
	cd lambda-deploy && pipenv install

# lint deploy script
lint:
	pipenv run flake8 "${DEPLOY_SCRIPT_SRC}" "${GH_RELEASE_SCRIPT_SRC}"
