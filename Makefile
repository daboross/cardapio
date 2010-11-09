PYTHON = `which python`

ifeq ($(DESTDIR),)
DESTDIR = 
endif

ifeq ($(PREFIX),)
PREFIX = $(DESTDIR)/usr
endif

all:
	@echo "make install - Install on local system"
	@echo "make uninstall - Remove from local system"
	@echo "make buildsrc - Generate a deb source package"
	@echo "make clean - Get rid of scratch and byte files"

install: install_docky_helper
	python -m compileall src/
	python -m compileall src/plugins/
	python -m compileall src/docky/

	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.pyc $(PREFIX)/lib/cardapio/
	cp -f src/cardapio.ui $(PREFIX)/lib/cardapio/
	cp -f res/cardapio.desktop $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/docky
	cp -f src/docky/DockySettingsHelper* $(PREFIX)/lib/cardapio/docky/
	cp -f src/docky/__init__* $(PREFIX)/lib/cardapio/docky/
	
	mkdir -p $(PREFIX)/share/pixmaps
	cp -f res/cardapio*.xcf $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.png $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.svg $(PREFIX)/share/pixmaps/
	
	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f src/plugins/* $(PREFIX)/lib/cardapio/plugins/
	
	mkdir -p $(PREFIX)/share/locale
	cp -rf locale/* $(PREFIX)/share/locale/
	
	mkdir -p $(PREFIX)/bin
	ln -fs $(PREFIX)/lib/cardapio/cardapio $(PREFIX)/bin/cardapio
	
	mkdir -p $(DESTDIR)/usr/lib/bonobo/servers
	cp -f src/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/

install_docky_helper:
	if test -d $(PREFIX)/share/dockmanager; then \
		cp -f src/docky/metadata/cardapio_helper.py.info $(PREFIX)/share/dockmanager/metadata/; \
		cp -f src/docky/scripts/cardapio_helper.py $(PREFIX)/share/dockmanager/scripts/; \
		chmod +x $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py; \
	fi

buildsrc:
	debuild -S

clean:
	$(MAKE) -f $(CURDIR)/debian/rules clean
	find . -name '*.pyc' -delete

uninstall: uninstall_docky_helper
	rm -rf $(PREFIX)/lib/cardapio
	rm -rf $(PREFIX)/bin/cardapio
	rm -rf $(PREFIX)/share/pixmaps/cardapio*
	rm $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	find $(PREFIX)/share/locale -name '*cardapio.mo' -delete

uninstall_docky_helper:
	if test -d $(PREFIX)/share/dockmanager; then\
		rm $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info; \
		rm $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py; \
	fi

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)
	# TODO: add docky stuff here

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/
	if test -d $(PREFIX)/share/dockmanager; then\
		rm $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info; \
		rm $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py; \
	fi

oldclean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete

