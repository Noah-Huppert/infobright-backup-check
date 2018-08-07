.PHONY: install lint

MAKE=make

# install deploy script and lambda function dependencies
install:
	${MAKE} -C deploy/ install
	${MAKE} -C ib_backup/ install

# lint the deploy script and step source files
lint:
	${MAKE} -C deploy/ lint
	${MAKE} -C ib_backup/ lint
