//
//  Copyright (c) 2011   Cardapio team
//

const St = imports.gi.St;
const Shell = imports.gi.Shell;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const Util = imports.misc.util;
const Mainloop = imports.mainloop
const Lang = imports.lang;

const DBus = imports.dbus;

const CardapioInterface = {
	name: 'org.varal.Cardapio',
	methods: [{
		name: 'show_hide_near_point',
		inSignature: 'iibb',
		outSignature: ''
	}, {
		name: 'is_visible',
		inSignature: '',
		outSignature: 'b'
	}, {
		name: 'set_default_window_position',
		inSignature: 'ii',
		outSignature: ''
	}]
};

let Cardapio = DBus.makeProxyClass(CardapioInterface);

function ApplicationsButton() {
	this._init.apply(this, arguments);
}

ApplicationsButton.prototype = {
	__proto__: PanelMenu.Button.prototype,

	_init: function() {
		PanelMenu.Button.prototype._init.call(this, 0.0);

		DBus.session.start_service('org.varal.Cardapio')
		this._cardapio = new Cardapio(DBus.session, 'org.varal.Cardapio', '/org/varal/Cardapio');

		// Below is a hack to make sure the service started above gets 
		// loaded before we run the set_default_window_positionRemote() 
		// method. Ugly, argh!
        Mainloop.timeout_add_seconds(1.0, Lang.bind(this, this._setDefaultWindowPosition));

		this._icon = new St.Icon({ 
			icon_name: 'start-here',
			icon_type: St.IconType.SYMBOLIC,
			icon_size: Main.panel.button.height 
		});

        this._label = new St.Label({text: 'Menu' });

		this._box = new St.BoxLayout({style_class: 'cardapio-box'});
		this._box.add(this._icon);
		this._box.add(this._label);

		this.actor.set_child(this._box);

		// add at the leftmost position
		//this.container = Main.panel._leftBox;
		//Main.panel._leftBox.insert_actor(this.actor, 0);

		// add immediately after hotspot
		this.container = Main.panel._leftBox;
		Main.panel._leftBox.insert_actor(this.actor, 1);

		// add to the left of the clock
		//this.container = Main.panel._centerBox;
		//Main.panel._centerBox.insert_actor(this.actor, 0);

		// add to the right of the clock
		//this.container = Main.panel._centerBox;
		//Main.panel._centerBox.insert_actor(this.actor, -1);

		// add at the right-most position
		//this.container = Main.panel._rightBox;
		//Main.panel._rightBox.insert_actor(this.actor, -1);
	},

	_setDefaultWindowPosition: function() {
		x = this.actor.get_x() + this.container.get_x();
		y = this.actor.get_y() + this.container.get_y();
		this._cardapio.set_default_window_positionRemote(x, y);
	},

    _onButtonPress: function(actor, event) {

		// just in case the user closed Cardapio in the 
		// meantime using Alt-F4, we restart it here
		DBus.session.start_service('org.varal.Cardapio')

		visible = this._cardapio.is_visibleRemote();

        if (visible)
            this.actor.add_style_pseudo_class('active');
        else
            this.actor.remove_style_pseudo_class('active');

		x = this.actor.get_x() + this.container.get_x();
		y = this.actor.get_y() + this.container.get_y();
		this._cardapio.show_hide_near_pointRemote(x, y, false, false);

		// in case the applet moved for some reason, save the new position now 
        Mainloop.timeout_add_seconds(1.0, Lang.bind(this, this._setDefaultWindowPosition));
		// (adding it to the Mainloop is a hack that makes sure this actually
		// runs. Otherwise, for some reason, it fails to execute...)
    },
};


function main(extensionMeta) {
	new ApplicationsButton();
}

