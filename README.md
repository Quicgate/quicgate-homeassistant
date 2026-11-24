# quicgate for Home Assistant

See how your [quicgate](https://github.com/Quicgate/quicgate) reverse proxy is doing from Home
Assistant, and switch proxy hosts on and off from a dashboard or an automation.

quicgate is a self-hosted reverse proxy manager in a single binary. This integration reads its
management API once a minute with a token that can do no more than that.

## What you get

One device per quicgate, with:

**A switch per host.** On means quicgate serves the host, off means it does not. The switch is
named after the host's first domain. Only there when the token may switch hosts.

**Problem indicators** that turn on when something needs attention, each with the details as
attributes:

| Indicator | Turns on when |
|---|---|
| Backends | a backend that a host forwards to does not answer |
| Certificates | a certificate could not be obtained or renewed, or one ends within two weeks |
| Ports | quicgate could not open a port it should listen on |
| VPN | the WireGuard endpoint is switched on but not running |

**Sensors:**

| Sensor | What it shows |
|---|---|
| Hosts switched on | how many hosts are on, and which are off |
| Backends unreachable | how many backends do not answer, with host and error |
| Days until first certificate expires | and which host that certificate is on |
| Certificates with a problem | how many could not be obtained or renewed, with the error |
| Requests last hour | with a split by HTTP version and by status |
| Blocked requests last hour | with a split by reason (access list, banned address, rate limit and so on) |
| Server errors last hour | responses in the 500 range |
| Data received / sent last hour | |
| Open connections | |
| Banned addresses | how many, and for each: the address, country, host and reason |
| Response time | the median, with the slowest 5 and 1 percent as attributes |
| Running since | when quicgate last started |

**A version check.** Home Assistant shows when a newer quicgate has been published, with a
link to what changed. It does not install anything: how you update quicgate stays yours.

**Per host, switched off until you want them:** "backend" (does this host's backend answer)
and "certificate expires" (when this host's certificate ends). Switch them on per host under
the device's entities. The overall indicators always name the host that has a problem, so you
only need these for hosts you want on a dashboard of their own.

## What it needs

- quicgate **1.19.0** or newer. That version added tokens that can be limited, and the status
  endpoint this integration reads.
- Home Assistant **2026.1** or newer. It is developed and tested on 2026.11.
- Home Assistant has to reach quicgate's admin port (81 unless you changed it).

## Installing

Through the Marketplace (called HACS before Home Assistant 2026.11), as a custom repository:

1. Open the **Marketplace**, open the menu in the top right corner and choose
   **Custom repositories**.
2. Enter `https://github.com/Quicgate/quicgate-homeassistant`, choose **Integration** as the
   type, and add it.
3. Find **quicgate** in the list, download it, and restart Home Assistant.

By hand: copy the folder `custom_components/quicgate` from this repository into the
`custom_components` folder of your Home Assistant configuration, and restart.

## Connecting

1. In quicgate, open your account menu, **API tokens**, **New token**. Give it a name and
   choose what it may do:
   - **Monitoring, and switch hosts on or off** for everything above, or
   - **Monitoring** if you only want to watch. You then get no switches.

   Copy the token: quicgate shows it once.
2. In Home Assistant, go to **Settings**, **Devices & services**, **Add integration**, and
   choose **quicgate**.
3. Enter the address of quicgate's admin interface, for example `http://192.168.1.10:81`, and
   the token.

Prefer the admin port itself over a domain name that quicgate proxies. If Home Assistant
reaches quicgate through one of quicgate's own proxy hosts, it loses sight of quicgate exactly
when that host has a problem.

A full access token works too, and the integration will ask whether you mean it. It needs no
more than a limited one, and Home Assistant keeps the token readable in its own storage.

## Things to know

- **Switching a host off takes it offline** for everyone until you switch it on again. If
  Home Assistant itself is reached through quicgate, do not switch that host off from outside
  your home: you would be switching off the way back in.
- The "last hour" sensors are a moving window over the past sixty minutes, not a counter that
  starts at zero every hour.
- Once every six hours Home Assistant asks GitHub for the newest quicgate release, for the
  version check. Nothing about your setup is sent along. Everything else stays between Home
  Assistant and your quicgate.
- A host you delete in quicgate disappears from Home Assistant at the next reading, and a host
  you add appears. A renamed host keeps its entity, with the new name.
- If quicgate stops accepting the token (you revoked it), Home Assistant asks for a new one
  under **Settings**, **Devices & services**.

## An example

A notification when a backend goes down:

```yaml
automation:
  - alias: "quicgate: a backend stopped answering"
    triggers:
      - trigger: state
        entity_id: binary_sensor.quicgate_backends
        to: "on"
        for: "00:03:00"
    actions:
      - action: notify.notify
        data:
          title: "quicgate"
          message: >
            Not answering:
            {{ state_attr('binary_sensor.quicgate_backends', 'unreachable')
               | map(attribute='host') | join(', ') }}
```

## Feedback

This is new. If something is wrong, unclear or missing, please
[open an issue](https://github.com/Quicgate/quicgate-homeassistant/issues).

## Licence

MIT, like quicgate itself.
