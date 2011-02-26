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
	python -m compileall src/gnomepanel/
	python -m compileall src/docky/
	
	# remove old files which have been renamed
	rm -rf $(PREFIX)/lib/cardapio/cardapio.py
	rm -rf $(PREFIX)/lib/cardapio/cardapio.pyc
	rm -rf $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.py
	rm -rf $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.pyc
	
	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/cardapio-gnome-panel-applet $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioPluginInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioPluginInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/OptionsWindow.py $(PREFIX)/lib/cardapio/
	cp -f src/OptionsWindow.pyc $(PREFIX)/lib/cardapio/
	cp -f src/misc.py $(PREFIX)/lib/cardapio/
	cp -f src/misc.pyc $(PREFIX)/lib/cardapio/
	cp -f src/IconHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/IconHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f src/SettingsHelper.py $(PREFIX)/lib/cardapio/
	cp -f src/SettingsHelper.pyc $(PREFIX)/lib/cardapio/
	cp -f res/cardapio.desktop $(PREFIX)/lib/cardapio/
	
	mkdir -p $(PREFIX)/lib/cardapio/ui
	cp -f src/ui/cardapio.ui $(PREFIX)/lib/cardapio/ui/
	cp -f src/ui/options.ui $(PREFIX)/lib/cardapio/ui/
	
	mkdir -p $(PREFIX)/lib/cardapio/gnomepanel
	cp -f src/gnomepanel/CardapioGnomeApplet* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/CardapioGnomeAppletFactory* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/__init__* $(PREFIX)/lib/cardapio/gnomepanel/
	
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
	ln -fs $(PREFIX)/lib/cardapio/cardapio-gnome-panel-applet $(PREFIX)/bin/cardapio-gnome-panel-applet
	
	mkdir -p $(DESTDIR)/usr/lib/bonobo/servers
	#cp -f src/gnomepanel/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/
	for f in locale/*; \
		do test -f $$f/LC_MESSAGES/cardapio.mo && msgunfmt -o $$f.po $$f/LC_MESSAGES/cardapio.mo || true; \
	done
	intltool-merge -b locale src/gnomepanel/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server

buildsrc:
	debuild -S

clean:
	$(MAKE) -f $(CURDIR)/debian/rules clean
	find . -name '*.pyc' -delete

uninstall: uninstall_docky_helper
	rm -rf $(PREFIX)/lib/cardapio
	rm -rf $(PREFIX)/bin/cardapio
	rm -rf $(PREFIX)/bin/cardapio-gnome-panel-applet 
	rm -rf $(PREFIX)/share/pixmaps/cardapio*
	rm -f $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	find $(PREFIX)/share/locale -name '*cardapio.mo' -delete

install_docky_helper:
	if test -d $(PREFIX)/share/dockmanager; then \
		cp -f src/docky/cardapio_helper.py.info $(PREFIX)/share/dockmanager/metadata/; \
		cp -f src/docky/cardapio_helper.py $(PREFIX)/share/dockmanager/scripts/; \
		chmod +x $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py; \
	fi

uninstall_docky_helper:
	if test -d $(PREFIX)/share/dockmanager; then\
		rm -rf $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info; \
		rm -rf $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py; \
	fi

oldinstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE)

olduninstall:
	$(PYTHON) setup.py install --root $(DESTDIR) --install-layout=deb $(COMPILE) --record file_list.txt
	cat file_list.txt | xargs rm -rf
	rm file_list.txt
	rm -rf /usr/lib/python2.6/dist-packages/cardapio/
	rm -rf /usr/local/lib/python2.6/dist-packages/cardapio/

oldclean:
	$(PYTHON) setup.py clean
	$(MAKE) -f $(CURDIR)/debian/rules clean
	rm -rf build/ MANIFEST
	find . -name '*.pyc' -delete


