PYTHON = `which python`

ifeq ($(DESTDIR),)
DESTDIR = debian/tmp
endif

ifeq ($(PREFIX),)
PREFIX = $(DESTDIR)/usr
endif

all: build
	@echo "make install - Install on local system"
	@echo "make uninstall - Remove from local system"
	@echo "make buildsrc - Generate a deb source package"
	@echo "make clean - Get rid of scratch and byte files"

build: updateversion
	@echo "Precompiling python bytecode..."
	python -m compileall src/
	python -m compileall src/plugins/
	python -m compileall src/awn/
	python -m compileall src/docky/
	python -m compileall src/gnomepanel/
	python -m compileall src/gnomeshell/
	@find . -name '*.py{,c}' -exec chmod 755 '{}' \;
	@echo "Precompiled python bytecode."

install: build
	# Common {
	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/cardapio $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.py $(PREFIX)/lib/cardapio/
	cp -f src/Cardapio.pyc $(PREFIX)/lib/cardapio/
	cp -f src/Constants.py $(PREFIX)/lib/cardapio/
	cp -f src/Constants.pyc $(PREFIX)/lib/cardapio/
	cp -f src/DesktopEnvironment.py $(PREFIX)/lib/cardapio/
	cp -f src/DesktopEnvironment.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioGtkView.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioViewInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioAppletInterface.pyc $(PREFIX)/lib/cardapio/
	cp -f src/CardapioSimpleDbusApplet.py $(PREFIX)/lib/cardapio/
	cp -f src/CardapioSimpleDbusApplet.pyc $(PREFIX)/lib/cardapio/
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
	cp -f res/cardapioDocky.desktop $(PREFIX)/lib/cardapio/

	mkdir -p $(PREFIX)/lib/cardapio/ui
	cp -f src/ui/cardapio.ui $(PREFIX)/lib/cardapio/ui/
	cp -f src/ui/options.ui $(PREFIX)/lib/cardapio/ui/

	mkdir -p $(PREFIX)/share/applications
	cp -f res/cardapio.desktop $(PREFIX)/share/applications/

	mkdir -p $(PREFIX)/share/pixmaps
	cp -f res/cardapio*.png $(PREFIX)/share/pixmaps/
	cp -f res/cardapio*.svg $(PREFIX)/share/pixmaps/

	mkdir -p $(PREFIX)/lib/cardapio/plugins
	cp -f src/plugins/* $(PREFIX)/lib/cardapio/plugins/

	mkdir -p $(PREFIX)/share/locale
	cp -rf locale/* $(PREFIX)/share/locale/
	# }

	# AWN {
	mkdir -p $(PREFIX)/lib/cardapio
	cp -f src/awn/CardapioAwnWrapper.py $(PREFIX)/lib/cardapio/
	cp -f src/awn/CardapioAwnWrapper.pyc $(PREFIX)/lib/cardapio/
	cp -f src/awn/CardapioAwnApplet.py $(PREFIX)/lib/cardapio/
	cp -f src/awn/CardapioAwnApplet.pyc $(PREFIX)/lib/cardapio/
	mkdir -p $(DESTDIR)/usr/share/avant-window-navigator/applets
	cp -f src/awn/cardapio.desktop $(DESTDIR)/usr/share/avant-window-navigator/applets
	# }

	# Docky {
	mkdir -p $(PREFIX)/lib/cardapio/docky
	mkdir -p $(PREFIX)/share/dockmanager/metadata/
	mkdir -p $(PREFIX)/share/dockmanager/scripts/

	cp -f src/docky/DockySettingsHelper* $(PREFIX)/lib/cardapio/docky/
	cp -f src/docky/__init__* $(PREFIX)/lib/cardapio/docky/
	cp -f src/docky/cardapio_helper.py.info $(PREFIX)/share/dockmanager/metadata/
	cp -f src/docky/cardapio_helper.py $(PREFIX)/share/dockmanager/scripts/
	cp -f src/docky/cardapio_helper.pyc $(PREFIX)/share/dockmanager/scripts/
	# }

	# GnomePanel { #
	mkdir -p $(PREFIX)/lib/cardapio/gnomepanel
	cp -f src/cardapio-gnome-panel-applet $(PREFIX)/lib/cardapio/
	cp -f src/gnomepanel/CardapioGnomeApplet* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/CardapioGnomeAppletFactory* $(PREFIX)/lib/cardapio/gnomepanel/
	cp -f src/gnomepanel/__init__* $(PREFIX)/lib/cardapio/gnomepanel/

	mkdir -p $(PREFIX)/bin
	ln -fs ../lib/cardapio/cardapio $(PREFIX)/bin/cardapio
	ln -fs ../lib/cardapio/cardapio-gnome-panel-applet $(PREFIX)/bin/cardapio-gnome-panel-applet

	mkdir -p $(DESTDIR)/usr/lib/bonobo/servers
	#cp -f src/gnomepanel/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/
	for f in locale/*; \
		do test -f $$f/LC_MESSAGES/cardapio.mo && msgunfmt -o $$f.po $$f/LC_MESSAGES/cardapio.mo || true; \
	done
	intltool-merge -b locale src/gnomepanel/cardapio.server $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server

	mkdir -p $(DESTDIR)/usr/share/dbus-1/services
	cp res/cardapio.service $(DESTDIR)/usr/share/dbus-1/services/cardapio.service
	# }

	# GnomeShell {
	mkdir -p $(PREFIX)/share/gnome-shell/extensions
	cp -rf src/gnomeshell/cardapio@varal.org $(PREFIX)/share/gnome-shell/extensions/
	# }

buildsrc:
	debuild -S

clean:
	find . -name '*.py{,c}' -delete

uninstall:
	rm -rf $(PREFIX)/lib/cardapio
	rm -rf $(PREFIX)/bin/cardapio
	rm -rf $(PREFIX)/share/pixmaps/cardapio*
	rm -f $(PREFIX)/share/applications/cardapio.desktop
	rm -f $(DESTDIR)/usr/lib/bonobo/servers/cardapio.server
	rm -f $(DESTDIR)/usr/share/dbus-1/services/cardapio.service
	find $(PREFIX)/share/locale -name '*cardapio.*' -delete

	# remove old files which have been renamed or moved to another package
	rm -f $(PREFIX)/lib/cardapio/cardapio.py*
	rm -f $(PREFIX)/lib/cardapio/plugins/firefox_bookmarks.py*

	# AWN
	rm -f $(PREFIX)/lib/cardapio/CardapioAwnWrapper.*
	rm -f $(PREFIX)/lib/cardapio/CardapioAwnApplet.*
	rm -f $(DESTDIR)/usr/share/avant-window-navigator/applets/cardapio.desktop

	# Gnome-Shell
	rm -rf $(PREFIX)/share/gnome-shell/extensions/cardapio@varal.org

	# Gnome-Panel
	rm -f $(PREFIX)/lib/cardapio/cardapio-gnome-panel-applet
	rm -f $(PREFIX)/bin/cardapio-gnome-panel-applet

	# Docky
	rm -f $(PREFIX)/share/dockmanager/metadata/cardapio_helper.py.info
	rm -f $(PREFIX)/share/dockmanager/scripts/cardapio_helper.py*

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

updateversion:
	echo $(MINOR_VERSION)
	sed -i 's/0\.9\.193/0\.9\.193/' \
	    'src/gnomeshell/cardapio@varal.org/metadata.json' \
	    'src/ui/cardapio.ui' \
	    'src/Cardapio.py' \
	    'setup.py'
