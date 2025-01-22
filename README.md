![BPS Logo](img/icon.png)
# ble_pos_sys
A BLE positioning sytem for Homeassistant providing realtime tracking indoors. Dependent on the Bermuda component built by @agattins. 

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=agittins&repository=bermuda&category=Integration)

- Precisely track your bluetooth devices (indoors) using using [bluetooth_proxy] [ESPHome](https://esphome.io/) (https://esphome.io/components/bluetooth_proxy.html) devices in [HomeAssistant](https://home-assistant.io/).

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

[![pre-commit][pre-commit-shield]][pre-commit]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

## What it does:

BLE Positioning System (BPS) continues on the great work by [@agittins](https://github.com/agittins/bermuda) and his [bermuda].
Based on Bermudas ability to, in near-realtime, estimate distance to an ESPHome devices running bluetooth_proxy BPS can leverage this information and by trilaterate give a precise position.

By placing the location of the bluetooth devices as well as defining specific zones, BPS can show:
- Where exactly a device is located on a floorplan (like a GPS on a map)
- Determine which floor you are currently on. Gives the ability to automate for changing floor.
- Determine which zone a device is currently in. Gives the ability to automate based on specific devices entering or leaving a zone. 

This is done for all devices you track with Bermuda so you can track different persons or objects and automate based on this.

For my specific purpose I use Sonoff NS Panels in all rooms of my house which I run esphome on. This together with other stationary bluetooth proxies I have good coverage to do trilataration.

Bermuda aims to let you track any bluetooth device, and have Homeassistant tell you where in your house that device is. The only extra hardware you need are esp32 devices running esphome that act as bluetooth proxies. Alternatively, Shelly Plus devices can also perform this function.

## What you need:

- Home Assistant up and running (duhh!)
- Bermuda [bermuda] installed and tracking at least one bluetooth device
- At least devices providing bluetooth proxy information to HA using esphome's `bluetooth_proxy` component. (it needs data from three devices to be able to track so if you only have three devices and you loose one due to distance it is not able to track)

@agittins write on the Bermuda readme:
"  I like the D1-Mini32 boards because they're cheap and easy to deploy.
  The Shelly Plus bluetooth proxy devices are reported to work well.
  Only natively-supported bluetooth devices are supported, meaning there's no current or planned support for MQTT devices etc.

- USB Bluetooth on your HA host is not ideal, since it does not timestamp the advertisement packets.
  However it can be used for simple "Home/Not Home" tracking, and Area distance support is enabled currently."

  I can from my own experience add NS Panel since I use them all around the house as replacement for wall switches and thus get great coverage.


- Install BPS via HACS: [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=agittins&repository=bermuda&category=Integration)

## Documentation and help - the Wiki

See [The Wiki](https://github.com/Hogster/ble_pos_sys/wiki/) for more info on how it works and how to configure for your home.

## Screenshots

After installing, the integration should be visible in Settings, Devices & Services


You will now also have a new panel in the side panel named "BPS"


![The integration, in Settings, Devices & Services](img/screenshots/integration.png)

Press the `CONFIGURE` button to see the configuration dialog. At the bottom is a field
where you can enter/list any bluetooth devices the system can see. Choosing devices
will add them to the configured devices list and creating sensor entities for them. See [How Do The Settings Work?](#how-do-the-settings-work) for more info.

![Bermuda integration configuration option flow](img/screenshots/configuration.png)

Choosing the device screen shows the current sensors and other info. Note that there are extra sensors in the "not shown" section that are disabled by default (the screenshot shows several of these enabled already). You can edit the properties of these to enable them for more detailed data on your device locations. This is primarily intended for troubleshooting or development, though.

![Screenshot of device information view](img/screenshots/deviceinfo.png)

The sensor information also includes attributes area name and id, relevant MAC addresses
etc.

![Bermuda sensor information](img/screenshots/sensor-info.png)

In Settings, People, you can define any Bermuda device to track home/away status
for any person/user.

![Assign a Bermuda sensor for Person tracking](img/screenshots/person-tracker.png)

## FAQ

See [The FAQ](https://github.com/agittins/bermuda/wiki/FAQ) in the Wiki!

## TODO / Ideas

- [ ] ~~Switch to performing updates on receipt of advertisements, instead of periodic polling~~ (nope, intervals work better)
- [ ] "Solve" realtime approximation of inter-proxy distances using Triangle Inequality
- [ ] Resolve x/y co-ordinates of all scanners and proxies (!)
- [ ] Some sort of map, just pick two proxies as an x-axis vector and go
- [ ] Config setting to define absolute locations of two proxies
- [ ] Support some way to "pin" more than two proxies/tags, and have it not break.
- [ ] An interface to define Areas in relation to the pinned proxies
- [ ] Experiment with some of
      [these algo's](https://mdpi-res.com/d_attachment/applsci/applsci-10-02003/article_deploy/applsci-10-02003.pdf?version=1584265508)
      for improving accuracy (too much math for me!). Particularly weighting shorter
      distances higher and perhaps the cosine similarity fingerprinting, possibly against
      fixed beacons as well to smooth environmental rssi fluctuations.

## Hacking tips

Wanna improve this? Awesome! Bear in mind this is my first ever HA
integration, and I'm much more greybeard sysadmin than programmer, so ~~if~~where
I'm doing stupid things I really would welcome some improvements!

You can start by using the service `bermuda.dump_devices` to examine the
internal state.

### Using `bermuda.dump_devices` service

Just calling the service `bermuda.dump_devices` will give you a full dump of the internal
data structures that bermuda uses to track and calculate its state. This can be helpful
for working out what's going on and troubleshooting, or to use if you have a very custom
need that you can solve with template sensors etc.

If called with no parameters, the service will return all data. parameters are available
which let you limit or reformat the resulting data to make it easier to work with. In particular
the `addresses` parameter is helpful to only return data relevant for one or more MAC addresses
(or iBeacon UUIDs).
See the information on parameters in the `Services` page in home assistant, under `Developer Tools`.

Important: If you decide to use the results of this call for your own templates etc, bear in mind that
the format might change in any release, and won't necessarily be considered a "breaking change".
This is beacuse the structure is used internally, rather than being a published API. That said, efforts will be made
to indicate in the release notes if fields in the structure are renamed or moved, but not for adding new
items.

## Prior Art

The `bluetooth_tracker` and `ble_tracker` integrations are only built to give a "home/not home"
determination, and don't do "Area" based location. (nb: "Zones" are places outside the
home, while "Areas" are rooms/areas inside the home). I wanted to be free to experiment with
this in ways that might not suit core, but hopefully at least some of this could find
a home in the core codebase one day.

The "monitor" script uses standalone Pi's to gather bluetooth data and then pumps it into
MQTT. It doesn't use the `bluetooth_proxy` capabilities which I feel are the future of
home bluetooth networking (well, it is for my home, anyway!).

ESPresense looks cool, but I don't want to dedicate my nodes to non-esphome use, and again
it doesn't leverage the bluetooth proxy features now in HA. I am probably reinventing
a fair amount of ESPresense's wheel.

## Installation

Definitely use the HACS interface! Once you have HACS installed, go to `Integrations`, click the
meatballs menu in the top right, and choose `Custom Repositories`. Paste `agittins/bermuda` into
the `Repository` field, and choose `Integration` for the `Category`. Click `Add`.

You should now be able to add the `Bermuda BLE Trilateration` integration. Once you have done that,
you need to restart Homeassistant, then in `Settings`, `Devices & Services` choose `Add Integration`
and search for `Bermuda BLE Trilateration`. It's possible that it will autodetect for you just by
noticing nearby bluetooth devices.

Once the integration is added, you need to set up your devices by clicking `Configure` in `Devices and Services`,
`Bermuda BLE Trilateration`.

In the `Configuration` dialog, you can choose which bluetooth devices you would like the integration to track.

The instructions below are the generic notes from the template:

1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `bermuda`.
4. Download _all_ the files from the `custom_components/bermuda/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant
7. In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "Bermuda BLE Trilateration"

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

## Credits

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template
[Cookiecutter User Guide](https://cookiecutter-homeassistant-custom-component.readthedocs.io/en/stable/quickstart.html)\*\*

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[buymecoffee]: https://buymeacoffee.com/hogster
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/Hogster/ble_pos_sys.svg?style=for-the-badge
[commits]: https://github.com/Hogster/ble_pos_sys/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/Hogster/ble_pos_sys.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40Hogster-blue.svg?style=for-the-badge
[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Hogster/ble_pos_sys.svg?style=for-the-badge
[releases]: https://github.com/Hogster/ble_pos_sys/releases
[user_profile]: https://github.com/Hogster
[bermuda]: https://github.com/agittins/bermuda
