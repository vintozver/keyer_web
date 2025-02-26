.PHONY: clean


clean:
	find build -delete || true
	find src/handler -name *.pyc -delete || true
	find src/module -name *.pyc -delete || true
	find src/util -name *.pyc -delete || true
	find src/config -name *.pyc -delete || true
	find src/handler -name __pycache__ -delete || true
	find src/module -name __pycache__ -delete || true
	find src/util -name __pycache__ -delete || true
	find src/config -name __pycache__ -delete || true

