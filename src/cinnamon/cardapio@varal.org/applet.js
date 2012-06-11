/*
  Cardapio is an alternative menu applet, launcher, and much more!

  Copyright (C) 2010 Cardapio Team (tvst@hotmail.com)

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

const Lang = imports.lang;
const Applet = imports.ui.applet;
const GLib = imports.gi.GLib;
const Gettext = imports.gettext.domain('cinnamon-applets');
const _ = Gettext.gettext;
const DBus = imports.dbus;

// set up dbus interface

const applet_interface_name   = 'org.varal.CardapioSimpleDbusApplet';
const applet_service_name     = 'org.varal.CardapioSimpleDbusApplet';
const applet_object_name      = '/org/varal/CardapioSimpleDbusApplet';

const cardapio_interface_name = 'org.varal.Cardapio';
const cardapio_service_name   = 'org.varal.Cardapio';
const cardapio_object_name    = '/org/varal/Cardapio';

const CardapioAppletInterface = {
	name: applet_interface_name,
	methods: [{
		name: 'configure_applet_button',
		inSignature: 'ss',
		outSignature: '',
	}],
	signals: [],
	properties: [],
};

const CardapioInterface = {
	name: cardapio_interface_name,
	methods: [{
		name: 'show_hide_near_point',
		inSignature: 'iibb',
		outSignature: '',
	}, {
		name: 'is_visible',
		inSignature: '',
		outSignature: 'b',
	}, {
		name: 'set_default_window_position',
		inSignature: 'iii',
		outSignature: '',
	}, {
		name: 'get_applet_configuration',
		inSignature: '',
		outSignature: 'ss',
	}, {
		name: 'quit',
		inSignature: '',
		outSignature: '',
	}],
	signals: [{
		name: 'on_cardapio_loaded',
		inSignature: '',	
	}],
	properties: [],
};

let Cardapio = DBus.makeProxyClass(CardapioInterface);

// applet code

function CardapioApplet(orientation) {
	this._init(orientation);
}

CardapioApplet.prototype = {

	__proto__: Applet.TextIconApplet.prototype,

	_init: function(orientation) {

		Applet.TextIconApplet.prototype._init.call(this, orientation);

		// set up applet button

		try {
			// temporary icon while loading
			// (it would be great if we could set this to show no icon at all)
			this.set_applet_icon_name('start-here');

			// while loading, display "...", but using unicode bullets
			this.set_applet_label('\u2022 \u2022 \u2022');

			this.set_applet_tooltip(_('Access applications, folders, system settings, etc.'));
		}
		catch (e) {
			global.logError(e);
			return;
		}

		// start the Cardapio service and try to connect to it

		DBus.session.start_service(cardapio_service_name);

		this._cardapio = new Cardapio(DBus.session, cardapio_service_name, cardapio_object_name);

		// in case Cardapio is already running and communicable, set up the applet
		this._cardapioServiceLoaded();

		// otherwise, only do it once Cardapio is fully loaded
		this._cardapio.connect('on_cardapio_loaded',
				Lang.bind(this, 
					function(emitter) {
						this._cardapioServiceLoaded();
					})
				);
	},

	_cardapioServiceLoaded: function() {

		this._cardapio.get_applet_configurationRemote(Lang.bind(this, 
			function(result, err) {
				if (!err) {
					this.configure_applet_button(result[0], result[1]);
				}
			})
		);

		this._setDefaultWindowPosition();
	},

	_setDefaultWindowPosition: function() {

		let x = this.actor.get_x() + this.container.get_x();
		let y = this.actor.get_y() + this.container.get_y();
		let d = 0; // TODO: fetch the display number here

		this._cardapio.set_default_window_positionRemote(x, y, d);
	},

	on_applet_clicked: function(event) {

		// just in case the user closed Cardapio in the 
		// meantime using Alt-F4, we restart it here
		DBus.session.start_service(cardapio_service_name)

		visible = this._cardapio.is_visibleRemote();

		if (visible) {
			this.actor.add_style_pseudo_class('active');
		}
		else {
			this.actor.remove_style_pseudo_class('active');
		}

		let x = this.actor.get_x() + this.container.get_x();
		let y = this.actor.get_y() + this.container.get_y();
		let d = 0; // TODO: fetch the display number here

		// TODO: add display to the DBus method below:
		this._cardapio.show_hide_near_pointRemote(x, y, false, false);

		// rerun this in case the applet moved on the screen
		this._setDefaultWindowPosition();
	},

	configure_applet_button: function(label_str, icon_path) {

		try {
			this.set_applet_label(label_str);
			this.set_applet_icon_path(icon_path);
		}
		catch (e) {
			global.logError(e);
			return;
		}
	},
};

function main(metadata, orientation) {
	let cardapioApplet = new CardapioApplet(orientation);
	return cardapioApplet;
}
