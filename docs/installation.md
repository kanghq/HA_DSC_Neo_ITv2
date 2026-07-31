# Installation

## 1. Prerequisites

- A DSC PowerSeries **Neo** panel (HS2016 / HS2032 / HS2064 / HS2128).
- A TL280-family communicator (TL280, TL280R, TL280RE, TL2803G, 3G2080, LE2080)
  wired to the panel's Corbus and connected to your LAN.
- Home Assistant 2024.11+ reachable from the communicator on the same network.
- Your **installer code** (factory default `5555`).
- A **static IP address or DHCP reservation** for the Home Assistant host. The
  panel dials out to a fixed IP; if HA's address changes, the panel can no
  longer connect.

## 2. Install the integration

### HACS (recommended)

1. HACS > **Integrations** > overflow menu > **Custom repositories**.
2. Repository: `https://github.com/LawPaul/HA_DSC_Neo_ITv2`, Category:
   **Integration**. Add.
3. Find **DSC PowerSeries Neo (ITv2)** in the list, click **Download**.
4. Restart Home Assistant.

### Manual

```bash
cd /config
mkdir -p custom_components
git clone https://github.com/LawPaul/HA_DSC_Neo_ITv2 /tmp/dsc
cp -r /tmp/dsc/custom_components/dsc_neo_itv2 custom_components/
```

Restart Home Assistant.

## 3. Program the panel

Everything below happens at a keypad in **installer programming**: press
`[*][8]` then enter the installer code. Navigate to a section by typing its
number. Press `[#]` to back out one level. When you are finished, press
`[*][9][9]` to leave installer mode.

> Write down the values you enter: you need the Integration ID and access key
> in step 4.

### Pick an integration group

The panel supports four independent integration groups, so a monitoring service
such as Alarm.com or NEO Go can occupy one while you use another. **Check which
groups are free before you write anything.** Read each group's server-IP section
below; a non-zero address means that group is in use, and overwriting it will
break that service.

| Setting | Group 1 | Group 2 | Group 3 | Group 4 |
|---|---|---|---|---|
| Type 1 access code | `423` | `450` | `477` | `504` |
| Integration options | `425` | `452` | `479` | `506` |
| Polling / notification options | `426` | `453` | `480` | `507` |
| Integration server IP | `428` | `455` | `482` | `509` |
| Integration server port | `429` | `456` | `483` | `510` |
| Type 2 access key | `700` | `701` | `702` | `703` |

Group subsections are offset by 27. The steps below use group 1; substitute
from the table if you are using another group.

### Section [851]: integration programming

| Section | Meaning | Value |
|---|---|---|
| `[851][422]` | **Integration identification number** | Read-only, 12 digits, shared by all four groups. Scroll right to reveal the last 6. Record it |
| `[851][425]` | Integration 1 options | Set bits 3, 4 and 5, clear everything else. The display should read `--345---` |
| `[851][426]` | Integration 1 polling / notification options | Set bit 3 only. The display should read `--3-----` |
| `[851][428]` | Integration 1 server IP | **The Home Assistant host IP**, entered 3 digits per octet (`192` `168` `001` `100`) |
| `[851][429]` | Integration 1 server port | **In hexadecimal.** `0C00` is 3072, the default |
| `[851][423]` | Integration access code (Type 1) | 8 hex digits, default `12345678`. Only needed for Type 1 |
| `[851][700]` | Integration access key (Type 2) | 32 hex digits, default `12345678123456781234567812345678`. Entered 8 characters at a time |

> The port in `[851][429]` is hexadecimal, not decimal. If you change Home
> Assistant's listen port from 3072, convert it: 3072 is `0C00`, 3073 is `0C01`.

> These section numbers are for communicator firmware v5.0 and later. Boards
> running v4.1 or earlier use different subsections and a different procedure.
> Check your TL280 revision against its installation manual first.

### Encryption type

- **Type 2** (recommended) uses the 32-hex-character key from `[851][700]`
  alone. Simpler, and what the config flow defaults to.
- **Type 1** uses the Integration ID from `[851][422]` combined with the 8-digit
  access code from `[851][423]`.

The panel decides which one to use during the handshake, so you do not have to
tell the integration which you programmed. Provide whichever key or keys match.

### Change the defaults

The factory defaults (`12345678...` / `5555`) are public knowledge. Change the
Type 2 key in `[851][700]` and the installer code before putting this into
production.

## 4. Add the integration in Home Assistant

**Settings > Devices & Services > Add Integration > "DSC PowerSeries Neo (ITv2)"**

### Step 1: Listen address

| Field | Default | Notes |
|---|---|---|
| Host | `0.0.0.0` | Interface to bind. Use a specific IP on multi-homed hosts. |
| Port | `3072` | Must match `[851][429]`, which is written in hex (`0C00`). |

The flow performs a pre-flight `bind()` and reports `port_in_use`,
`host_unavailable`, `bind_denied` or `bind_failed` immediately rather than
failing silently later.

### Step 2: Wait for panel

The flow now binds the listener and waits (up to 120 s) for the panel to dial
in. It reads the **Integration ID** and **encryption type** out of the handshake;
you do not type them.

If nothing happens, check `[851][428]` really holds the Home Assistant IP and
that `[851][425]` reads `--345---`, then force the panel to connect:

- Exit and re-enter installer programming, or
- Power-cycle the communicator.

Errors: `timeout_no_panel` (nothing connected in 120 s), `bind_failed`,
`probe_failed`.

### Step 3: Codes

| Field | Required | Notes |
|---|---|---|
| Type 2 access key | Yes | 32 hex characters from `[851][700]` |
| Type 1 access code | No | 8 digits from `[851][423]`, only if the panel uses Type 1 |
| User PIN | No | 4-6 digits. If set, HA will not prompt for a code when arming/disarming |
| Installer code | No | 4-6 digits. Enables reading zone definitions, partition assignments and PGM types from the panel |

Submitting creates the config entry, titled `DSC Neo <integration-id>`. The
Integration ID is used as the entry's unique id, so the same panel cannot be
added twice.

## 5. Verify

1. `binary_sensor.<panel>_panel_connection` should be **Connected**.
2. `sensor.<panel>_communicator_firmware` should show a version string.
3. Open a door: the matching zone binary sensor should flip within a second.

If not, see [Troubleshooting](troubleshooting.md).

## Updating

HACS: update from the HACS UI, then restart Home Assistant.

Manual: replace `custom_components/dsc_neo_itv2/` with the new version and
restart.

Config entries survive updates. If a release changes the config-entry schema, a
migration runs automatically on startup.

## Removal

1. **Settings > Devices & Services > DSC PowerSeries Neo (ITv2) > overflow menu > Delete.**
   This unloads the listener, removes all entities and devices, and clears the
   cached panel config from `.storage/`.
2. Remove the integration from HACS (or delete
   `config/custom_components/dsc_neo_itv2/`).
3. Restart Home Assistant.
4. At the keypad, clear the integration server IP in `[851][428]` so the panel
   stops dialling a host that no longer answers.
