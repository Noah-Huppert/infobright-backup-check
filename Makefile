.PHONY: lint

MAKE=make

# lint the deploy script and step source files
lint:
	${MAKE} -C deploy/ lint
	${MAKE} -C ib_backup/ lint
