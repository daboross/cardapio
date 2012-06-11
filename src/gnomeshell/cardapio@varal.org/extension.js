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

const St = imports.gi.St;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const Mainloop = imports.mainloop
const Lang = imports.lang;
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

function CardapioApplet() {
	this._init.apply(this, arguments);
}

CardapioApplet.prototype = {

	__proto__: PanelMenu.Button.prototype,

	_init: function() {

		PanelMenu.Button.prototype._init.call(this, 0.0);
		
		this.actor = new St.Bin({
			style_class: 'panel-button',
			reactive: true,
			can_focus: true,
			x_fill: true,
			y_fill: false,
			track_hover: true,
		});

		this.actor._delegate = this;
		this.actor.connect('button-press-event', Lang.bind(this, this._onButtonPress));		

		this._dbus_name_id = DBus.session.acquire_name(applet_service_name, 0, null, null);
		DBus.session.exportObject(applet_object_name, this);

		this._icon = new St.Icon({ 
			icon_type: St.IconType.SYMBOLIC,
			icon_size: Main.panel._leftBox.height 
		});

		this._label = new St.Label();

		// while loading, display "...", but using unicode bullets
		this.configure_applet_button('\u2022 \u2022 \u2022', '');

		this._box = new St.BoxLayout({style_class: 'cardapio-box'});
		this._box.add(this._icon);
		this._box.add(this._label);

		this.actor.set_child(this._box);

		// TODO: make this a setting

		// add at the leftmost position
		//this.container = Main.panel._leftBox;
		//Main.panel._leftBox.insert_child_at_index(this.actor, 0);

		// add immediately after hotspot
		this.container = Main.panel._leftBox;
		Main.panel._leftBox.insert_child_at_index(this.actor, 1);

		// add at the end of the left box
		//this.container = Main.panel._leftBox;
		//Main.panel._leftBox.add(this.actor);

		// add to the left of the clock
		//this.container = Main.panel._centerBox;
		//Main.panel._centerBox.insert_child_at_index(this.actor, 0);

		// add to the right of the clock
		//this.container = Main.panel._centerBox;
		//Main.panel._centerBox.insert_child_at_index(this.actor, -1);

		// add at the right-most position
		//this.container = Main.panel._rightBox;
		//Main.panel._rightBox.insert_child_at_index(this.actor, -1);

		// TODO: create a setting for setting up a hotspot

		DBus.session.start_service(cardapio_service_name);

		this._cardapio = new Cardapio(DBus.session, cardapio_service_name, cardapio_object_name);

		// in case Cardapio is already running and communicable, set up the applet
		this._cardapioServiceLoaded();

		// otherwise, only do it once Cardapio is fully loaded
		this._cardapio.connect('on_cardapio_loaded', Lang.bind(this, 
			function(emitter) {
				this._cardapioServiceLoaded();
			})
		);

		// Old code: instead of using signals, we just had a timeout
		//Mainloop.timeout_add_seconds(1.0, Lang.bind(this, this._cardapioServiceLoaded));
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

	_onButtonPress: function(actor, event) {

		// just in case the user closed Cardapio in the 
		// meantime using Alt-F4, we restart it here
		DBus.session.start_service(cardapio_service_name)

		visible = this._cardapio.is_visibleRemote();

		if (visible)
			this.actor.add_style_pseudo_class('active');
		else
			this.actor.remove_style_pseudo_class('active');

		let x = this.actor.get_x() + this.container.get_x();
		let y = this.actor.get_y() + this.container.get_y();
		let d = 0; // TODO: fetch the display number here

		// TODO: add display to the DBus method below:
		this._cardapio.show_hide_near_pointRemote(x, y, false, false);

		// rerun this in case the applet moved on the screen
		this._setDefaultWindowPosition();
	},

	configure_applet_button: function(label_str, icon_path) {

		if (label_str.length > 0) {
			this._label.set_text(label_str);
			this._label.show();
		}
		else {
			this._label.hide();
		}

		if (icon_path.length > 0) {
			this._icon.set_icon_name(icon_path);
			this._icon.show();
		}
		else {
			this._icon.hide();
		}
	},

	destroy: function() {

		this._cardapio.quitRemote();

		DBus.session.unexportObject(this);
		DBus.session.release_name_by_id(this._dbus_name_id);
		
		this.container.remove_actor(this.actor);
		delete this;
	},
};

DBus.conformExport(CardapioApplet.prototype, CardapioAppletInterface);


// old API

function main(extensionMeta) {
	new CardapioApplet();
}


// new API

let cardapioApplet;

function init(extensionMeta) {
	DBus.session.start_service(cardapio_service_name)
}

function enable() {
	cardapioApplet = new CardapioApplet();
}

function disable() {
	cardapioApplet.destroy();
}

