.PHONY: clean static_ext_full static_ext_min static_ext_jquery_ui


src/static_ext:
	mkdir -p src/static_ext


clean:
	find src/handler -name *.pyc -delete
	find src/module -name *.pyc -delete
	find src/util -name *.pyc -delete
	find src/config -name *.pyc -delete
	find src/handler -name __pycache__ -delete
	find src/module -name __pycache__ -delete
	find src/util -name __pycache__ -delete
	find src/config -name __pycache__ -delete


static_ext_full: src/static_ext static_ext_jquery_ui
	curl -o src/static_ext/sprintf.js "https://raw.githubusercontent.com/alexei/sprintf.js/refs/heads/master/src/sprintf.js"
	curl -o src/static_ext/jquery.js "https://code.jquery.com/jquery-3.6.0.js"


static_ext_min: src/static_ext static_ext_jquery_ui
	curl -o src/static_ext/sprintf.js "https://raw.githubusercontent.com/alexei/sprintf.js/refs/heads/master/dist/sprintf.min.js"
	curl -o src/static_ext/jquery.js "https://code.jquery.com/jquery-3.6.0.min.js"


static_ext_jquery_ui: build
	curl -o "build/static_jquery-ui.zip" "https://jqueryui.com/resources/download/jquery-ui-1.14.1.zip"
	mkdir -p src/static_ext/jquery-ui
	unzip -p "build/static_jquery-ui.zip" jquery-ui-1.14.1/jquery-ui.min.css > src/static_ext/jquery-ui/main.css
	unzip -p "build/static_jquery-ui.zip" jquery-ui-1.14.1/jquery-ui.structure.min.css > src/static_ext/jquery-ui/structure.css
	unzip -p "build/static_jquery-ui.zip" jquery-ui-1.14.1/jquery-ui.theme.min.css > src/static_ext/jquery-ui/theme.css
	unzip -p "build/static_jquery-ui.zip" jquery-ui-1.14.1/jquery-ui.min.js > src/static_ext/jquery-ui/main.js
	mkdir -p src/static_ext/jquery-ui/images
	unzip -o -j "build/static_jquery-ui.zip" "jquery-ui-1.14.1/images/*" -d src/static_ext/jquery-ui/images/


build:
	mkdir -p build


